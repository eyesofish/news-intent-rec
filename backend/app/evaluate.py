"""Offline ranking metrics for V1.

Pure functions only - no DB, no HTTP, no settings. Drivers in scripts/ are
responsible for collecting per-event prediction / ground-truth pairs and
feeding them to these functions. Tested in tests/test_evaluate.py against
the default (non-mysql) pytest layer.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TimeSplit:
    """Result of a chronological train / val / test split.

    `split_ts_train_val` is the event_ts of the last train event, and
    `split_ts_val_test` is the event_ts of the last val event (falling back
    to the train boundary when val is empty). Both are None when the input
    is empty.
    """

    train: list[dict[str, Any]]
    val: list[dict[str, Any]]
    test: list[dict[str, Any]]
    split_ts_train_val: int | None
    split_ts_val_test: int | None


def time_split(
    events: Iterable[dict[str, Any]],
    *,
    train_ratio: float = 0.8,
    val_ratio: float = 0.0,
    ts_key: str = "event_ts",
) -> TimeSplit:
    """Sort events by ts_key, then cut by cumulative-count fraction.

    With val_ratio == 0.0 the val list is empty and the split degenerates
    to train / test only. Ties on ts_key preserve sorted-stable order.
    """
    if train_ratio < 0 or val_ratio < 0 or train_ratio + val_ratio > 1.0:
        raise ValueError("ratios must be in [0,1] and sum to <= 1.0")
    ordered = sorted(events, key=lambda e: int(e[ts_key]))
    n = len(ordered)
    if n == 0:
        return TimeSplit(train=[], val=[], test=[], split_ts_train_val=None, split_ts_val_test=None)
    n_train = min(round(n * train_ratio), n)
    n_val = min(round(n * val_ratio), n - n_train)
    train = ordered[:n_train]
    val = ordered[n_train : n_train + n_val]
    test = ordered[n_train + n_val :]
    split_tv = int(train[-1][ts_key]) if train else None
    split_vt = int(val[-1][ts_key]) if val else split_tv
    return TimeSplit(
        train=train,
        val=val,
        test=test,
        split_ts_train_val=split_tv,
        split_ts_val_test=split_vt,
    )


def recall_at_k(predicted: Sequence[int], relevant: Iterable[int], k: int) -> float:
    """|relevant intersect predicted[:k]| / |relevant|.

    Returns 0.0 when k <= 0 or `relevant` is empty. For single-relevant-per-query
    evaluation callers should pass `relevant=[article_id]`; the returned value is
    then 1.0 if hit, 0.0 otherwise, and per-query averages give Hit Rate @K.
    """
    if k <= 0:
        return 0.0
    rel_set = set(relevant)
    if not rel_set:
        return 0.0
    top_k = list(predicted)[:k]
    hits = sum(1 for a in top_k if a in rel_set)
    return hits / len(rel_set)


def ndcg_at_k(predicted: Sequence[int], relevant: Iterable[int], k: int) -> float:
    """Standard binary-gain NDCG@k.

    DCG = sum_{i=1..k} rel_i / log2(i + 1) over 1-indexed positions.
    IDCG = sum_{i=1..min(|relevant|, k)} 1 / log2(i + 1).
    Returns 0.0 when k <= 0, `relevant` is empty, or no relevant items
    appear in `predicted[:k]`.
    """
    if k <= 0:
        return 0.0
    rel_set = set(relevant)
    if not rel_set:
        return 0.0
    top_k = list(predicted)[:k]
    dcg = sum(1.0 / math.log2(i + 1) for i, a in enumerate(top_k, start=1) if a in rel_set)
    ideal_hits = min(len(rel_set), k)
    idcg = sum(1.0 / math.log2(i + 1) for i in range(1, ideal_hits + 1))
    return dcg / idcg if idcg > 0 else 0.0


def graded_ndcg_at_k(
    predicted: Sequence[int],
    relevance: Mapping[int, float],
    k: int,
) -> float:
    if k <= 0 or not relevance:
        return 0.0
    top_k = list(predicted)[:k]
    dcg = sum(
        (2.0 ** float(relevance.get(article_id, 0.0)) - 1.0) / math.log2(rank + 1)
        for rank, article_id in enumerate(top_k, start=1)
    )
    ideal_gains = sorted(
        (2.0 ** float(value) - 1.0 for value in relevance.values() if value > 0),
        reverse=True,
    )[:k]
    idcg = sum(gain / math.log2(rank + 1) for rank, gain in enumerate(ideal_gains, start=1))
    return dcg / idcg if idcg > 0 else 0.0


def mrr_at_k(predicted: Sequence[int], relevant: Iterable[int], k: int) -> float:
    if k <= 0:
        return 0.0
    relevant_ids = set(relevant)
    for rank, article_id in enumerate(list(predicted)[:k], start=1):
        if article_id in relevant_ids:
            return 1.0 / rank
    return 0.0
