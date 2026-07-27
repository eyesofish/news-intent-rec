from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a pooled search relevance review set.")
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "build" / "search_eval" / "candidate_report.json",
    )
    parser.add_argument(
        "--queries",
        type=Path,
        default=ROOT / "evaluation" / "search_relevance" / "queries.jsonl",
    )
    parser.add_argument(
        "--qrels",
        type=Path,
        default=ROOT / "evaluation" / "search_relevance" / "qrels.jsonl",
    )
    parser.add_argument(
        "--normalized-dir",
        type=Path,
        default=ROOT / "build" / "mind_normalized",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "search_eval" / "review_pool.jsonl",
    )
    parser.add_argument("--per-arm", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    queries = {str(row["query_id"]): row for row in _read_jsonl(args.queries)}
    existing_qrels = {
        (str(row["query_id"]), int(row["article_id"])): row for row in _read_jsonl(args.qrels)
    }

    pooled: dict[str, dict[int, dict[str, Any]]] = {}
    for query_id, query in queries.items():
        pooled[query_id] = {
            int(article_id): {"anchor": True, "arm_ranks": {}}
            for article_id in query.get("anchor_article_ids", [])
        }
    for arm_name, arm in report["arms"].items():
        for row in arm["queries"]:
            query_id = str(row["query_id"])
            article_ids = row.get("candidate_article_ids", row["article_ids"])
            for rank, article_id in enumerate(article_ids[: args.per_arm], start=1):
                candidate = pooled[query_id].setdefault(
                    int(article_id),
                    {"anchor": False, "arm_ranks": {}},
                )
                candidate["arm_ranks"][arm_name] = rank

    article_ids = sorted(
        {article_id for candidates in pooled.values() for article_id in candidates}
    )
    rows = pq.read_table(
        args.normalized_dir / "articles.parquet",
        filters=[("article_id", "in", article_ids)],
        columns=["article_id", "headline", "abstract", "category", "subcategory"],
    ).to_pylist()
    article_by_id = {int(row["article_id"]): row for row in rows}

    output_rows = []
    for query_id in sorted(queries):
        query = queries[query_id]
        for article_id, candidate in sorted(
            pooled[query_id].items(),
            key=lambda item: (
                not bool(item[1]["anchor"]),
                min(item[1]["arm_ranks"].values(), default=999),
                item[0],
            ),
        ):
            article = article_by_id[article_id]
            qrel = existing_qrels.get((query_id, article_id))
            output_rows.append(
                {
                    "query_id": query_id,
                    "query_text": query["text"],
                    "slice": query["slice"],
                    "split": query["split"],
                    "intended_meaning": query["intended_meaning"],
                    "expected_relevant": query["expected_relevant"],
                    "article_id": article_id,
                    "headline": article["headline"],
                    "abstract": article["abstract"],
                    "category": article["category"],
                    "subcategory": article["subcategory"],
                    "anchor": candidate["anchor"],
                    "arm_ranks": candidate["arm_ranks"],
                    "existing_relevance": qrel["relevance"] if qrel else None,
                    "label_source": qrel["label_source"] if qrel else None,
                    "human_reviewed": qrel["human_reviewed"] if qrel else False,
                }
            )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in output_rows),
        encoding="utf-8",
    )
    print(
        f"wrote {args.output}: queries={len(queries)} judgments={len(output_rows)} "
        f"articles={len(article_ids)}"
    )


if __name__ == "__main__":
    main()
