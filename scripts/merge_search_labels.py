from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge pooled search relevance labels.")
    parser.add_argument(
        "--pool",
        type=Path,
        default=ROOT / "build" / "search_eval" / "review_pool.jsonl",
    )
    parser.add_argument(
        "--labels-dir",
        type=Path,
        default=ROOT / "build" / "search_eval",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "evaluation" / "search_relevance" / "qrels.jsonl",
    )
    parser.add_argument(
        "--manifest-output",
        type=Path,
        default=ROOT / "evaluation" / "search_relevance" / "label_manifest.json",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    pool_rows = _read_jsonl(args.pool)
    pool_keys = {(str(row["query_id"]), int(row["article_id"])) for row in pool_rows}
    label_paths = sorted(args.labels_dir.glob("labels_q*.jsonl"))
    if not label_paths:
        raise SystemExit(f"No label files found in {args.labels_dir}")

    labels: dict[tuple[str, int], dict[str, Any]] = {}
    for path in label_paths:
        for row in _read_jsonl(path):
            key = (str(row["query_id"]), int(row["article_id"]))
            if key in labels:
                raise ValueError(f"duplicate label across files: {key}")
            relevance = int(row["relevance"])
            if relevance not in {0, 1, 2}:
                raise ValueError(f"invalid relevance for {key}: {relevance}")
            labels[key] = row

    label_keys = set(labels)
    if label_keys != pool_keys:
        raise ValueError(
            f"label/pool mismatch: missing={len(pool_keys - label_keys)} "
            f"extra={len(label_keys - pool_keys)}"
        )

    output_rows = [
        {
            "query_id": query_id,
            "article_id": article_id,
            "relevance": int(row["relevance"]),
            "confidence": str(row["confidence"]),
            "label_source": str(row["label_source"]),
            "human_reviewed": bool(row["human_reviewed"]),
        }
        for (query_id, article_id), row in sorted(labels.items())
    ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in output_rows),
        encoding="utf-8",
    )

    grade_counts = Counter(int(row["relevance"]) for row in output_rows)
    confidence_counts = Counter(str(row["confidence"]) for row in output_rows)
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    manifest = {
        "query_count": len({row["query_id"] for row in output_rows}),
        "judgment_count": len(output_rows),
        "grade_counts": {str(key): value for key, value in sorted(grade_counts.items())},
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "label_source": "ai_assisted_pool",
        "human_review_status": "pending_spot_check",
        "qrels_sha256": digest,
        "source_label_files": [path.name for path in label_paths],
    }
    args.manifest_output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"wrote {args.output}: judgments={len(output_rows)} "
        f"grades={dict(sorted(grade_counts.items()))}"
    )


if __name__ == "__main__":
    main()
