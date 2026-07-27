from __future__ import annotations

import json
from pathlib import Path

import faiss
import numpy as np
import pytest

from backend.app.search_retrieval import (
    DenseSearchIndex,
    HybridSearchConfig,
    HybridSearchIndex,
    SearchArtifactError,
    SearchDocument,
    file_sha256,
    write_search_documents,
)


class FakeEncoder:
    def encode(
        self,
        sentences: str | list[str],
        *,
        batch_size: int = 32,
        show_progress_bar: bool = False,
        convert_to_numpy: bool = True,
        normalize_embeddings: bool = True,
    ) -> np.ndarray:
        del batch_size, show_progress_bar, convert_to_numpy, normalize_embeddings
        if isinstance(sentences, list):
            return np.array([[1.0, 0.0] for _ in sentences], dtype=np.float32)
        return np.array([1.0, 0.0], dtype=np.float32)


def _write_artifact(tmp_path: Path) -> Path:
    documents = [
        SearchDocument(
            article_id=10,
            headline="Football tactics",
            abstract="Defensive formations.",
            category="sports",
            subcategory="football_nfl",
        ),
        SearchDocument(
            article_id=20,
            headline="Celebrity awards",
            abstract="Red carpet fashion.",
            category="entertainment",
            subcategory="celebrity",
        ),
    ]
    write_search_documents(tmp_path / "documents.jsonl", documents)
    (tmp_path / "article_id_map.json").write_text(
        json.dumps({"index_to_article_id": [10, 20]}),
        encoding="utf-8",
    )
    index = faiss.IndexFlatIP(2)
    index.add(np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32))
    faiss.write_index(index, str(tmp_path / "dense.faiss"))
    metadata = {
        "schema_version": 1,
        "source_fingerprint": "fixture",
        "document_count": 2,
        "model_id": "fixture/model",
        "model_revision": "fixture-revision",
        "similarity": "cosine_via_normalized_inner_product",
        "hybrid_config": HybridSearchConfig(
            min_dense_score=0.5,
            min_bm25_score=100.0,
        ).to_dict(),
        "file_sha256": {
            name: file_sha256(tmp_path / name)
            for name in ("documents.jsonl", "article_id_map.json", "dense.faiss")
        },
    }
    (tmp_path / "metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )
    return tmp_path


def test_dense_artifact_loads_and_searches_with_injected_encoder(tmp_path: Path):
    artifact_dir = _write_artifact(tmp_path)

    index = DenseSearchIndex.load(
        artifact_dir,
        expected_source_fingerprint="fixture",
        encoder_factory=lambda _model, _revision: FakeEncoder(),
    )

    hits = index.search("football strategy", limit=2)
    assert [hit.article_id for hit in hits] == [10, 20]
    assert hits[0].score == pytest.approx(1.0)


def test_hybrid_artifact_applies_confidence_guard(tmp_path: Path):
    artifact_dir = _write_artifact(tmp_path)
    index = HybridSearchIndex.load(
        artifact_dir,
        expected_source_fingerprint="fixture",
        encoder_factory=lambda _model, _revision: FakeEncoder(),
    )

    result = index.search("football tactics", limit=2)

    assert result.accepted is True
    assert result.hits[0].article_id == 10
    assert result.top_dense_score == pytest.approx(1.0)


def test_dense_artifact_rejects_hash_mismatch(tmp_path: Path):
    artifact_dir = _write_artifact(tmp_path)
    (artifact_dir / "documents.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(SearchArtifactError, match="hash mismatch"):
        DenseSearchIndex.load(
            artifact_dir,
            encoder_factory=lambda _model, _revision: FakeEncoder(),
        )
