from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass

ItemSimilarity = Callable[[int, int], float | None]


@dataclass(frozen=True)
class MMRConfig:
    similarity_penalty: float


@dataclass(frozen=True)
class MMRCandidate[T]:
    article_id: int
    relevance: float
    topic_ids: frozenset[int]
    value: T


@dataclass(frozen=True)
class MMRSelection[T]:
    value: T
    article_id: int
    relevance: float
    max_similarity: float
    mmr_score: float


MMR_EXPERIMENT_CONFIGS: dict[str, MMRConfig] = {
    "lgb_plus_als_plus_search_mmr": MMRConfig(similarity_penalty=0.02),
}


def mmr_config(experiment_arm: str) -> MMRConfig | None:
    return MMR_EXPERIMENT_CONFIGS.get(experiment_arm)


def topic_jaccard(left: frozenset[int], right: frozenset[int]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def hybrid_item_similarity(
    left_article_id: int,
    left_topic_ids: frozenset[int],
    right_article_id: int,
    right_topic_ids: frozenset[int],
    *,
    als_similarity: ItemSimilarity,
) -> float:
    als_score = als_similarity(left_article_id, right_article_id)
    if als_score is not None and math.isfinite(als_score):
        return min(1.0, max(0.0, als_score))
    return topic_jaccard(left_topic_ids, right_topic_ids)


def rerank_mmr[T](
    candidates: Sequence[MMRCandidate[T]],
    *,
    limit: int,
    similarity_penalty: float,
    als_similarity: ItemSimilarity,
) -> list[MMRSelection[T]]:
    if limit <= 0 or not candidates:
        return []
    if similarity_penalty < 0:
        raise ValueError("similarity_penalty must be non-negative")

    remaining = list(range(len(candidates)))
    max_similarities = [0.0] * len(candidates)
    selected: list[MMRSelection[T]] = []

    while remaining and len(selected) < limit:
        best_index = min(
            remaining,
            key=lambda index: (
                -(candidates[index].relevance - similarity_penalty * max_similarities[index]),
                -candidates[index].relevance,
                candidates[index].article_id,
            ),
        )
        candidate = candidates[best_index]
        max_similarity = max_similarities[best_index]
        selected.append(
            MMRSelection(
                value=candidate.value,
                article_id=candidate.article_id,
                relevance=candidate.relevance,
                max_similarity=max_similarity,
                mmr_score=candidate.relevance - similarity_penalty * max_similarity,
            )
        )
        remaining.remove(best_index)
        if len(selected) >= limit:
            break

        for index in remaining:
            similarity = hybrid_item_similarity(
                candidate.article_id,
                candidate.topic_ids,
                candidates[index].article_id,
                candidates[index].topic_ids,
                als_similarity=als_similarity,
            )
            max_similarities[index] = max(max_similarities[index], similarity)

    return selected
