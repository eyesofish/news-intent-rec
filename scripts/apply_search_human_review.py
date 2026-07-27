from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply an approved human label spot-check.")
    parser.add_argument(
        "--sample",
        type=Path,
        default=ROOT / "build" / "search_eval" / "human_review_sample.json",
    )
    parser.add_argument(
        "--qrels",
        type=Path,
        default=ROOT / "evaluation" / "search_relevance" / "qrels.jsonl",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "evaluation" / "search_relevance" / "label_manifest.json",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    sample = json.loads(args.sample.read_text(encoding="utf-8"))
    approved = {
        (str(row["query_id"]), int(row["article_id"])): int(row["proposed_relevance"])
        for row in sample
    }
    if len(approved) != len(sample):
        raise ValueError("human review sample contains duplicate query/article pairs")

    rows = _read_jsonl(args.qrels)
    matched: set[tuple[str, int]] = set()
    for row in rows:
        key = (str(row["query_id"]), int(row["article_id"]))
        if key not in approved:
            continue
        if int(row["relevance"]) != approved[key]:
            raise ValueError(f"approved relevance does not match qrels for {key}")
        row["human_reviewed"] = True
        row["label_source"] = "ai_assisted_pool_human_spot_checked"
        matched.add(key)
    if matched != set(approved):
        raise ValueError(f"human review sample references missing qrels: {set(approved) - matched}")

    args.qrels.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    manifest.update(
        {
            "human_review_status": "approved_stratified_spot_check",
            "human_reviewed_judgment_count": len(approved),
            "human_reviewed_query_count": len({query_id for query_id, _ in approved}),
            "human_review_sample_sha256": hashlib.sha256(args.sample.read_bytes()).hexdigest(),
            "qrels_sha256": hashlib.sha256(args.qrels.read_bytes()).hexdigest(),
        }
    )
    args.manifest.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"marked {len(approved)} qrels as human spot-checked")


if __name__ == "__main__":
    main()
