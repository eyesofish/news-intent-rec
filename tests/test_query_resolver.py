from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from backend.app.errors import SearchIndexNotReadyError, UnresolvedQueryError
from backend.app.repositories._utils import is_numeric_query_key
from backend.app.repositories.query_resolver import resolve_query_key, resolve_search_query
from backend.app.search_retrieval import HybridHit, HybridSearchResult


class FakeCursor:
    """Tiny SQL cursor stub.

    A test supplies a sequence of canned result sets (``script``); each call
    to ``execute`` pops the next set and ``fetchone``/``fetchall`` reads it.
    A ``predicate`` optionally inspects each ``execute`` call.
    """

    def __init__(
        self,
        script: list[list[dict[str, Any]]],
        on_execute: Callable[[str, tuple], None] | None = None,
    ) -> None:
        self._script = script
        self._current: list[dict[str, Any]] = []
        self.executed: list[tuple[str, tuple]] = []
        self._on_execute = on_execute

    def __enter__(self) -> FakeCursor:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def execute(self, sql: str, params: tuple = ()) -> None:
        self.executed.append((sql, params))
        if self._on_execute is not None:
            self._on_execute(sql, params)
        self._current = self._script.pop(0) if self._script else []

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self._current)

    def fetchone(self) -> dict[str, Any] | None:
        return self._current[0] if self._current else None


class FakeConnection:
    def __init__(
        self,
        script: list[list[dict[str, Any]]],
        on_execute: Callable[[str, tuple], None] | None = None,
    ) -> None:
        self._cursor = FakeCursor(script, on_execute=on_execute)

    def cursor(self) -> FakeCursor:
        return self._cursor


class FakeHybridIndex:
    def __init__(self, result: HybridSearchResult) -> None:
        self.result = result
        self.queries: list[tuple[str, int]] = []

    def search(self, query_text: str, *, limit: int) -> HybridSearchResult:
        self.queries.append((query_text, limit))
        return self.result


# ── is_numeric_query_key ────────────────────────────────────────────────────


def test_is_numeric_query_key_accepts_space_separated_ints():
    assert is_numeric_query_key("248 12125") is True
    assert is_numeric_query_key("  248   12125  ") is True
    assert is_numeric_query_key("0") is True


def test_is_numeric_query_key_rejects_text_and_blank():
    assert is_numeric_query_key("Falafel") is False
    assert is_numeric_query_key("火锅") is False
    assert is_numeric_query_key("") is False
    assert is_numeric_query_key("   ") is False
    assert is_numeric_query_key("248 abc") is False


# ── numeric pass-through ────────────────────────────────────────────────────


def test_resolve_passes_numeric_query_key_through_without_db_lookup():
    connection = FakeConnection(script=[])
    resolved = resolve_query_key(connection, "248 12125", query_text=None)
    assert resolved == "248 12125"
    assert connection._cursor.executed == []


def test_resolve_normalizes_numeric_query_key_whitespace():
    connection = FakeConnection(script=[])
    resolved = resolve_query_key(connection, "  248   12125  ", query_text=None)
    assert resolved == "248 12125"


# ── display_query exact / prefix / contains ────────────────────────────────


def test_resolve_matches_display_query_exact():
    connection = FakeConnection(script=[[{"query_key": "100 200", "row_count": 3}]])
    resolved = resolve_query_key(connection, None, query_text="Falafel")
    assert resolved == "100 200"
    sql, params = connection._cursor.executed[0]
    assert "LOWER(display_query) = LOWER(%s)" in sql
    assert params == ("Falafel",)


def test_resolve_matches_display_query_prefix_after_exact_miss():
    connection = FakeConnection(
        script=[
            [],  # exact display_query miss
            [{"query_key": "300", "row_count": 2}],  # prefix hit
        ]
    )
    resolved = resolve_query_key(connection, None, query_text="Fala")
    assert resolved == "300"
    assert connection._cursor.executed[1][1] == ("fala%",)


def test_resolve_matches_display_query_contains_after_prefix_miss():
    connection = FakeConnection(
        script=[
            [],
            [],
            [{"query_key": "777", "row_count": 1}],
        ]
    )
    resolved = resolve_query_key(connection, None, query_text="alaf")
    assert resolved == "777"
    assert connection._cursor.executed[2][1] == ("%alaf%",)


# ── topic.display_name fallback chain ──────────────────────────────────────


def test_resolve_falls_back_to_topic_display_name_exact():
    connection = FakeConnection(
        script=[
            [],  # display_query exact
            [],  # display_query prefix
            [],  # display_query contains
            [{"topic_id": 9}],  # topic.display_name exact
            [{"query_key": "555", "best_score": 0.9}],  # topic → query_key
        ]
    )
    resolved = resolve_query_key(connection, None, query_text="Falafel")
    assert resolved == "555"
    topic_sql, topic_params = connection._cursor.executed[3]
    assert "LOWER(display_name) = LOWER(%s)" in topic_sql
    assert topic_params == ("Falafel",)


def test_resolve_uses_topic_display_name_contains_match():
    connection = FakeConnection(
        script=[
            [],
            [],
            [],
            [],  # topic exact miss
            [],  # topic prefix miss
            [{"topic_id": 12}],  # topic contains hit
            [{"query_key": "888", "best_score": 0.5}],
        ]
    )
    resolved = resolve_query_key(connection, None, query_text="honey")
    assert resolved == "888"


# ── article headline/abstract fallback ─────────────────────────────────────


def test_resolve_falls_back_to_real_article_text():
    connection = FakeConnection(
        script=[
            [],
            [],
            [],
            [],
            [],
            [],
            [{"query_key": "42", "best_score": 1.0}],
        ]
    )

    resolved = resolve_query_key(connection, None, query_text="quarterback")

    assert resolved == "42"
    sql, params = connection._cursor.executed[-1]
    assert "LOWER(q.display_title) LIKE %s" in sql
    assert params == ("%quarterback%", "%quarterback%")


def test_resolve_does_not_lexically_match_short_text():
    connection = FakeConnection(script=[[], [], [], [], [], []])

    with pytest.raises(UnresolvedQueryError):
        resolve_query_key(connection, None, query_text="ai")

    assert len(connection._cursor.executed) == 6


# ── unresolved → 422 path ──────────────────────────────────────────────────


def test_resolve_raises_when_nothing_matches():
    connection = FakeConnection(script=[[], [], [], [], [], [], []])
    with pytest.raises(UnresolvedQueryError) as exc_info:
        resolve_query_key(connection, None, query_text="xyzzy-not-a-topic")
    assert exc_info.value.query_input == "xyzzy-not-a-topic"


def test_resolve_raises_when_topic_match_has_no_query_key():
    connection = FakeConnection(
        script=[
            [],
            [],
            [],
            [{"topic_id": 999}],  # topic exact hit
            [],  # but no query_topic_map row covers it
            [],  # prefix
            [],  # contains
            [],  # article text
        ]
    )
    with pytest.raises(UnresolvedQueryError):
        resolve_query_key(connection, None, query_text="Ceviche")


def test_resolve_raises_when_inputs_are_blank():
    connection = FakeConnection(script=[])
    with pytest.raises(UnresolvedQueryError):
        resolve_query_key(connection, "   ", query_text=None)
    assert connection._cursor.executed == []


# ── input precedence: query_text wins over a non-numeric query_key ─────────


def test_resolve_prefers_query_text_when_query_key_is_text():
    connection = FakeConnection(script=[[{"query_key": "42", "row_count": 1}]])
    resolved = resolve_query_key(connection, "ignored", query_text="Biryani")
    assert resolved == "42"
    assert connection._cursor.executed[0][1] == ("Biryani",)


def test_resolve_uses_query_key_as_text_when_query_text_absent():
    connection = FakeConnection(script=[[{"query_key": "11", "row_count": 1}]])
    resolved = resolve_query_key(connection, "Falafel", query_text=None)
    assert resolved == "11"
    assert connection._cursor.executed[0][1] == ("Falafel",)


# ── tiebreaker: deterministic ordering ─────────────────────────────────────


def test_resolve_display_query_tiebreaker_picks_lowest_query_key():
    # The resolver only LIMIT-1s, so the SQL ORDER BY clause is what
    # enforces tiebreakers. Verify the clause appears in the executed SQL.
    connection = FakeConnection(script=[[{"query_key": "100", "row_count": 5}]])
    resolve_query_key(connection, None, query_text="Falafel")
    sql, _ = connection._cursor.executed[0]
    assert "ORDER BY row_count DESC, query_key ASC" in sql


def test_hybrid_mode_preserves_exact_alias_without_loading_candidates():
    connection = FakeConnection(script=[[{"query_key": "250", "row_count": 1}]])
    index = FakeHybridIndex(
        HybridSearchResult(
            accepted=False,
            hits=(),
            top_dense_score=0.0,
            top_bm25_score=0.0,
            fusion_margin=0.0,
        )
    )

    resolution = resolve_search_query(
        connection,
        None,
        "football_nfl",
        retrieval_mode="hybrid_v1",
        hybrid_index=index,  # type: ignore[arg-type]
    )

    assert resolution.query_key == "250"
    assert resolution.source == "exact_alias"
    assert index.queries == []


def test_hybrid_mode_maps_article_hits_to_canonical_query_key():
    hit = HybridHit(
        article_id=42,
        bm25_score=12.0,
        dense_score=0.7,
        fusion_score=0.03,
        bm25_rank=1,
        dense_rank=1,
    )
    connection = FakeConnection(
        script=[
            [],
            [],
            [{"answer_id": 42, "topic_id": 14, "source_rank": 0}],
            [{"query_key": "14", "topic_id": 14, "score": 1.0, "match_rank": 1}],
        ]
    )
    index = FakeHybridIndex(
        HybridSearchResult(
            accepted=True,
            hits=(hit,),
            top_dense_score=0.7,
            top_bm25_score=12.0,
            fusion_margin=0.01,
        )
    )

    resolution = resolve_search_query(
        connection,
        None,
        "football tactics",
        retrieval_mode="hybrid_v1",
        hybrid_index=index,  # type: ignore[arg-type]
        hybrid_limit=50,
    )

    assert resolution.query_key == "14"
    assert resolution.source == "hybrid_v1"
    assert resolution.confidence == pytest.approx(0.7)
    assert resolution.hybrid_hits == (hit,)
    assert index.queries == [("football tactics", 50)]


def test_hybrid_mode_falls_back_to_top_hit_topic_when_alias_map_is_missing():
    top_hit = HybridHit(
        article_id=42,
        bm25_score=12.0,
        dense_score=0.7,
        fusion_score=0.03,
        bm25_rank=1,
        dense_rank=1,
    )
    second_hit = HybridHit(
        article_id=7,
        bm25_score=10.0,
        dense_score=0.6,
        fusion_score=0.02,
        bm25_rank=2,
        dense_rank=2,
    )
    connection = FakeConnection(
        script=[
            [],
            [],
            [
                {"answer_id": 7, "topic_id": 2, "source_rank": 0},
                {"answer_id": 42, "topic_id": 14, "source_rank": 0},
            ],
            [],
        ]
    )
    index = FakeHybridIndex(
        HybridSearchResult(
            accepted=True,
            hits=(top_hit, second_hit),
            top_dense_score=0.7,
            top_bm25_score=12.0,
            fusion_margin=0.01,
        )
    )

    resolution = resolve_search_query(
        connection,
        None,
        "football tactics",
        retrieval_mode="hybrid_v1",
        hybrid_index=index,  # type: ignore[arg-type]
    )

    assert resolution.query_key == "14"
    assert resolution.source == "hybrid_v1"


def test_hybrid_mode_rejects_low_confidence_query():
    connection = FakeConnection(script=[[], []])
    index = FakeHybridIndex(
        HybridSearchResult(
            accepted=False,
            hits=(),
            top_dense_score=0.2,
            top_bm25_score=3.0,
            fusion_margin=0.0,
        )
    )

    with pytest.raises(UnresolvedQueryError):
        resolve_search_query(
            connection,
            None,
            "kubernetes ingress controller",
            retrieval_mode="hybrid_v1",
            hybrid_index=index,  # type: ignore[arg-type]
        )


def test_hybrid_mode_requires_loaded_index_after_exact_alias_miss():
    connection = FakeConnection(script=[[], []])

    with pytest.raises(SearchIndexNotReadyError):
        resolve_search_query(
            connection,
            None,
            "football tactics",
            retrieval_mode="hybrid_v1",
            hybrid_index=None,
        )
