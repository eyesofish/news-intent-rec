from __future__ import annotations

import pytest

from backend.app.repositories.mmr import MMRCandidate, rerank_mmr


def _candidate(
    article_id: int,
    relevance: float,
    topics: set[int],
) -> MMRCandidate[int]:
    return MMRCandidate(
        article_id=article_id,
        relevance=relevance,
        topic_ids=frozenset(topics),
        value=article_id,
    )


def test_mmr_penalizes_redundant_topic_candidates():
    candidates = [
        _candidate(1, 0.90, {10}),
        _candidate(2, 0.89, {10}),
        _candidate(3, 0.80, {20}),
    ]

    selected = rerank_mmr(
        candidates,
        limit=3,
        similarity_penalty=0.20,
        als_similarity=lambda _left, _right: None,
    )

    assert [row.article_id for row in selected] == [1, 3, 2]
    assert selected[1].max_similarity == 0.0
    assert selected[2].max_similarity == 1.0


def test_mmr_prefers_als_similarity_when_both_vectors_exist():
    candidates = [
        _candidate(1, 0.90, {10}),
        _candidate(2, 0.85, {10}),
        _candidate(3, 0.84, {20}),
    ]
    similarities = {
        frozenset({1, 2}): -0.2,
        frozenset({1, 3}): 0.9,
        frozenset({2, 3}): 0.1,
    }

    selected = rerank_mmr(
        candidates,
        limit=3,
        similarity_penalty=0.20,
        als_similarity=lambda left, right: similarities[frozenset({left, right})],
    )

    assert [row.article_id for row in selected] == [1, 2, 3]
    assert selected[1].max_similarity == 0.0


def test_mmr_falls_back_to_jaccard_when_an_als_vector_is_missing():
    candidates = [
        _candidate(1, 0.90, {10, 11}),
        _candidate(2, 0.88, {10, 11}),
        _candidate(3, 0.80, {20}),
    ]

    selected = rerank_mmr(
        candidates,
        limit=2,
        similarity_penalty=0.20,
        als_similarity=lambda left, right: 0.5 if {left, right} == {1, 3} else None,
    )

    assert [row.article_id for row in selected] == [1, 3]


def test_zero_penalty_matches_relevance_order_and_tie_breaks_by_article_id():
    candidates = [
        _candidate(3, 0.80, {10}),
        _candidate(1, 0.90, {20}),
        _candidate(2, 0.90, {30}),
    ]

    selected = rerank_mmr(
        candidates,
        limit=3,
        similarity_penalty=0.0,
        als_similarity=lambda _left, _right: 1.0,
    )

    assert [row.article_id for row in selected] == [1, 2, 3]


def test_mmr_updates_similarity_incrementally():
    calls = 0

    def similarity(_left: int, _right: int) -> float:
        nonlocal calls
        calls += 1
        return 0.0

    selected = rerank_mmr(
        [_candidate(index, 1.0 - index / 100, {index}) for index in range(5)],
        limit=3,
        similarity_penalty=0.1,
        als_similarity=similarity,
    )

    assert len(selected) == 3
    assert calls == 7


def test_mmr_rejects_negative_penalty():
    with pytest.raises(ValueError, match="non-negative"):
        rerank_mmr(
            [_candidate(1, 1.0, set())],
            limit=1,
            similarity_penalty=-0.1,
            als_similarity=lambda _left, _right: None,
        )
