from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from scripts.eval_search_relevance import (
    _hybrid_default_gate,
    _paired_bootstrap_delta,
    evaluate_search_relevance,
)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_search_relevance_report_compares_lexical_and_bm25(tmp_path: Path):
    normalized_dir = tmp_path / "normalized"
    normalized_dir.mkdir()
    pq.write_table(
        pa.Table.from_pylist(
            [
                {
                    "article_id": 1,
                    "headline": "NFL defensive tactics",
                    "abstract": "Football coaches explain formations.",
                    "category": "sports",
                    "subcategory": "football_nfl",
                    "category_topic_id": 14,
                    "subcategory_topic_id": 250,
                },
                {
                    "article_id": 2,
                    "headline": "Celebrity red carpet",
                    "abstract": "Awards fashion.",
                    "category": "entertainment",
                    "subcategory": "celebrity",
                    "category_topic_id": 2,
                    "subcategory_topic_id": 45,
                },
            ]
        ),
        normalized_dir / "articles.parquet",
    )
    (normalized_dir / "normalization_manifest.json").write_text(
        json.dumps({"dataset": "fixture", "normalized_fingerprint": "fixture-hash"}),
        encoding="utf-8",
    )
    queries = tmp_path / "queries.jsonl"
    qrels = tmp_path / "qrels.jsonl"
    config = tmp_path / "config.json"
    _write_jsonl(
        queries,
        [
            {
                "query_id": "q1",
                "text": "defensive football strategy",
                "slice": "paraphrase",
                "split": "test",
                "intended_meaning": "NFL defensive tactics",
                "expected_relevant": True,
                "anchor_article_ids": [1],
            },
            {
                "query_id": "q2",
                "text": "quantum banana compiler",
                "slice": "ood",
                "split": "test",
                "intended_meaning": "unrelated",
                "expected_relevant": False,
                "anchor_article_ids": [],
            },
        ],
    )
    _write_jsonl(
        qrels,
        [
            {
                "query_id": "q1",
                "article_id": 1,
                "relevance": 2,
                "label_source": "fixture",
                "human_reviewed": True,
            }
        ],
    )
    config.write_text(
        json.dumps({"min_bm25_score": 0.0}),
        encoding="utf-8",
    )

    report = evaluate_search_relevance(
        normalized_dir=normalized_dir,
        queries_path=queries,
        qrels_path=qrels,
        arms=("lexical_v1", "bm25_v1"),
        config_path=config,
    )

    assert report["article_count"] == 2
    assert report["query_count"] == 2
    assert set(report["arms"]) == {"lexical_v1", "bm25_v1"}
    assert report["arms"]["lexical_v1"]["aggregate"]["reject_accuracy"] == 1.0
    assert report["arms"]["bm25_v1"]["aggregate"]["recall@10"] == 1.0
    assert "does not estimate CTR" in report["evidence_boundary"]


def test_paired_bootstrap_and_default_gate_require_safe_held_out_gain():
    baseline_rows = [
        {
            "query_id": f"q{index}",
            "split": "test",
            "false_reject": False,
            "ndcg@10": 0.1,
        }
        for index in range(10)
    ]
    hybrid_rows = [
        {
            "query_id": f"q{index}",
            "split": "test",
            "false_reject": False,
            "ndcg@10": 0.8,
        }
        for index in range(10)
    ]
    interval = _paired_bootstrap_delta(
        baseline_rows,
        hybrid_rows,
        metric="ndcg@10",
        samples=200,
    )
    results = {
        "lexical_v1": {
            "by_split": {
                "test": {
                    "recall@10": 0.2,
                    "reject_accuracy": 0.0,
                    "false_reject_rate": 0.0,
                }
            }
        },
        "hybrid_v1": {
            "by_split": {
                "test": {
                    "recall@10": 0.8,
                    "reject_accuracy": 1.0,
                    "false_reject_rate": 0.0,
                }
            }
        },
    }
    comparisons = {"hybrid_v1_vs_lexical_v1": {"ndcg@10": interval}}

    gate = _hybrid_default_gate(results, comparisons)

    assert interval["ci95_lower"] > 0
    assert gate["metrics_passed"] is True
    assert gate["recommended_default"] == "hybrid_v1"
