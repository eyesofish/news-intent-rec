from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.config import SearchRetrievalMode
from backend.app.errors import SearchIndexNotReadyError, UnresolvedQueryError
from backend.app.repositories._utils import (
    is_numeric_query_key,
    normalize_query_key,
    placeholders,
)
from backend.app.search_retrieval import HybridHit, HybridSearchIndex


@dataclass(frozen=True)
class QueryResolution:
    query_key: str
    source: str
    confidence: float = 1.0
    hybrid_hits: tuple[HybridHit, ...] = ()


def _match_display_query(
    connection: Any,
    text: str,
    *,
    exact_only: bool = False,
) -> str | None:
    """Try to resolve ``text`` against ``query_topic_map.display_query``.

    Runs three SQL passes (exact case-insensitive, prefix, contains) and
    returns the first non-empty hit, ordered deterministically by the row
    count of each candidate ``query_key`` (a proxy for "best/widest match")
    then ``query_key`` ascending.
    """
    like_prefix = f"{text.lower()}%"
    like_contains = f"%{text.lower()}%"
    passes: list[tuple[str, tuple[Any, ...]]] = [
        ("LOWER(display_query) = LOWER(%s)", (text,)),
        ("LOWER(display_query) LIKE %s", (like_prefix,)),
        ("LOWER(display_query) LIKE %s", (like_contains,)),
    ]
    if exact_only:
        passes = passes[:1]
    for predicate, params in passes:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT query_key, COUNT(*) AS row_count
                FROM query_topic_map
                WHERE {predicate}
                GROUP BY query_key
                ORDER BY row_count DESC, query_key ASC
                LIMIT 1
                """,
                params,
            )
            row = cursor.fetchone()
        if row:
            return str(row["query_key"])
    return None


def _match_topic_display_name(
    connection: Any,
    text: str,
    *,
    exact_only: bool = False,
) -> str | None:
    """Try to resolve ``text`` via ``topic.display_name`` → best query_key.

    Same three-stage chain (exact → prefix → contains). At each stage we
    gather matching ``topic_id`` values, then pick the ``query_key`` from
    ``query_topic_map`` with the highest ``MAX(score)`` covering any of
    those topics.
    """
    like_prefix = f"{text.lower()}%"
    like_contains = f"%{text.lower()}%"
    passes: list[tuple[str, tuple[Any, ...]]] = [
        ("LOWER(display_name) = LOWER(%s)", (text,)),
        ("LOWER(display_name) LIKE %s", (like_prefix,)),
        ("LOWER(display_name) LIKE %s", (like_contains,)),
    ]
    if exact_only:
        passes = passes[:1]
    for predicate, params in passes:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT topic_id
                FROM topic
                WHERE {predicate}
                ORDER BY answer_count DESC, topic_id ASC
                LIMIT 20
                """,
                params,
            )
            topic_ids = [int(row["topic_id"]) for row in cursor.fetchall()]
        if not topic_ids:
            continue
        ph = placeholders(topic_ids)
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT query_key, MAX(score) AS best_score
                FROM query_topic_map
                WHERE topic_id IN ({ph})
                GROUP BY query_key
                ORDER BY best_score DESC, query_key ASC
                LIMIT 1
                """,
                tuple(topic_ids),
            )
            row = cursor.fetchone()
        if row:
            return str(row["query_key"])
    return None


def _match_article_text(connection: Any, text: str) -> str | None:
    normalized = " ".join(text.lower().split())
    tokens = [token for token in normalized.split() if len(token) >= 3][:5]
    search_terms = [term for term in (normalized, *tokens) if len(term) >= 3]
    search_terms = list(dict.fromkeys(search_terms))
    if not search_terms:
        return None
    predicates = []
    params: list[str] = []
    for term in search_terms:
        predicates.append("(LOWER(q.display_title) LIKE %s OR LOWER(a.display_summary) LIKE %s)")
        contains = f"%{term}%"
        params.extend((contains, contains))
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT qtm.query_key, MAX(qtm.score) AS best_score
            FROM answer a
            JOIN question q ON q.question_id = a.question_id
            JOIN answer_topic at ON at.answer_id = a.answer_id
            JOIN query_topic_map qtm ON qtm.topic_id = at.topic_id
            WHERE {" OR ".join(predicates)}
            GROUP BY qtm.query_key
            ORDER BY best_score DESC, qtm.query_key ASC
            LIMIT 1
            """,
            tuple(params),
        )
        row = cursor.fetchone()
    return str(row["query_key"]) if row else None


def _query_key_from_hybrid_hits(
    connection: Any,
    hits: tuple[HybridHit, ...],
) -> str | None:
    selected_hits = hits[:10]
    if not selected_hits:
        return None
    score_by_article = {hit.article_id: max(hit.fusion_score, 1e-9) for hit in selected_hits}
    article_ids = list(score_by_article)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT answer_id, topic_id, source_rank
            FROM answer_topic
            WHERE answer_id IN ({placeholders(article_ids)})
            ORDER BY answer_id, source_rank ASC, topic_id ASC
            """,
            tuple(article_ids),
        )
        topic_rows = cursor.fetchall()
    topic_scores: dict[int, float] = {}
    first_topic_id: int | None = None
    any_topic_id: int | None = None
    top_article_id = selected_hits[0].article_id
    for row in topic_rows:
        article_id = int(row["answer_id"])
        article_score = score_by_article.get(article_id, 0.0)
        source_weight = 1.25 if int(row.get("source_rank") or 0) > 0 else 1.0
        topic_id = int(row["topic_id"])
        if any_topic_id is None:
            any_topic_id = topic_id
        if first_topic_id is None and article_id == top_article_id:
            first_topic_id = topic_id
        topic_scores[topic_id] = topic_scores.get(topic_id, 0.0) + (article_score * source_weight)
    if not topic_scores:
        return None
    if first_topic_id is None:
        first_topic_id = any_topic_id

    topic_ids = list(topic_scores)
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT query_key, topic_id, score, match_rank
            FROM query_topic_map
            WHERE topic_id IN ({placeholders(topic_ids)})
            ORDER BY query_key ASC, match_rank ASC
            """,
            tuple(topic_ids),
        )
        query_rows = cursor.fetchall()
    candidates = [
        (
            topic_scores[int(row["topic_id"])] * float(row.get("score") or 0.0),
            int(row.get("match_rank") or 0),
            str(row["query_key"]),
        )
        for row in query_rows
    ]
    if not candidates:
        if first_topic_id is None:
            return None
        return str(first_topic_id)
    _score, _rank, query_key = sorted(
        candidates,
        key=lambda row: (-row[0], row[1], row[2]),
    )[0]
    return query_key


def resolve_search_query(
    connection: Any,
    query_key: str | None,
    query_text: str | None,
    *,
    retrieval_mode: SearchRetrievalMode,
    hybrid_index: HybridSearchIndex | None = None,
    hybrid_limit: int = 200,
) -> QueryResolution:
    if query_key and is_numeric_query_key(query_key):
        return QueryResolution(
            query_key=normalize_query_key(query_key),
            source="numeric_query_key",
        )

    candidate = (query_text or query_key or "").strip()
    if not candidate:
        raise UnresolvedQueryError(candidate)

    if retrieval_mode == "hybrid_v1":
        resolved = _match_display_query(connection, candidate, exact_only=True)
        if resolved is None:
            resolved = _match_topic_display_name(connection, candidate, exact_only=True)
        if resolved is not None:
            return QueryResolution(
                query_key=normalize_query_key(resolved),
                source="exact_alias",
            )
        if hybrid_index is None:
            raise SearchIndexNotReadyError("artifact loader returned no index")
        result = hybrid_index.search(candidate, limit=hybrid_limit)
        if not result.accepted:
            raise UnresolvedQueryError(candidate)
        resolved = _query_key_from_hybrid_hits(connection, result.hits)
        if resolved is None:
            raise UnresolvedQueryError(candidate)
        return QueryResolution(
            query_key=normalize_query_key(resolved),
            source="hybrid_v1",
            confidence=result.top_dense_score,
            hybrid_hits=result.hits,
        )

    resolved = _match_display_query(connection, candidate)
    if resolved is None:
        resolved = _match_topic_display_name(connection, candidate)
    if resolved is None:
        resolved = _match_article_text(connection, candidate)
    if resolved is None:
        raise UnresolvedQueryError(candidate)
    return QueryResolution(
        query_key=normalize_query_key(resolved),
        source="lexical_v1",
    )


def resolve_query_key(
    connection: Any,
    query_key: str | None,
    query_text: str | None,
) -> str:
    """Resolve user-typed search input to a numeric ``query_key``.

    Resolution chain:

    1. If ``query_key`` already looks numeric, normalize and return.
    2. Otherwise pick the candidate text (``query_text`` first, else
       ``query_key``) and try matching ``query_topic_map.display_query``.
    3. Fall back to matching ``topic.display_name``.
    4. Fall back to real article headline/abstract lexical matches.
    5. If nothing matches, raise :class:`UnresolvedQueryError`.
    """
    return resolve_search_query(
        connection,
        query_key,
        query_text,
        retrieval_mode="lexical_v1",
    ).query_key
