# MIND Search Relevance Evaluation

## Scope and evidence boundary

The search upgrade is evaluated on the full normalized MIND-small catalog:

- 65,238 articles;
- 48 fixed English queries;
- 24 calibration queries and 24 held-out test queries;
- lexical, synonym, natural-language paraphrase, spelling/noise, and unrelated/OOD
  slices;
- 1,239 pooled judgments from lexical, BM25, dense, and hybrid candidates;
- AI-assisted labels with a user-approved 12-row stratified human spot-check.

MIND contains no observed search logs. These metrics measure offline relevance on this
fixed labeled set; they do not estimate CTR, causal user benefit, or production quality.
The online demo still indexes only the 174 articles in `build/mind_demo_world`.
Because BM25 IDF magnitude is corpus-size dependent, the demo artifact keeps the
full-corpus fusion weights but uses a separate checked-in
`evaluation/search_relevance/online_demo_config.json` confidence profile. This profile
is runtime behavior configuration, not part of the reported full-corpus relevance
metrics.

Machine-readable evidence:

- `docs/metrics/mind_search_relevance.json`
- `docs/metrics/mind_search_latency.json`
- `evaluation/search_relevance/queries.jsonl`
- `evaluation/search_relevance/qrels.jsonl`
- `evaluation/search_relevance/label_manifest.json`
- `evaluation/search_relevance/calibration_report.json`
- `evaluation/search_relevance/selected_config.json`

## Implemented retrieval path

```text
numeric query_key
  -> normalize and preserve

exact display/category alias
  -> high-precision topic lookup

other free text
  -> deterministic BM25 top-50
  -> all-MiniLM-L6-v2 query embedding
  -> normalized FAISS IndexFlatIP top-50
  -> weighted reciprocal-rank fusion
  -> calibrated confidence gate
  -> high-confidence articles only
  -> aggregate article topics to a canonical query_key
  -> persist search intent for the existing feed feedback loop
```

The online implementation is in:

- `backend/app/search_retrieval.py`
- `backend/app/repositories/query_resolver.py::resolve_search_query`
- `backend/app/repositories/content_dao.py::load_search_candidates`
- `backend/app/repositories/mysql.py::MysqlRuntimeRepository.search`

Search no longer fills a short result page with unrelated hot articles. A low-confidence
free-text query returns 422 `unresolved_query`. Missing or incompatible hybrid artifacts
return 503 `search_index_not_ready` and fail readiness instead of silently falling back.

## Calibration

`scripts/calibrate_search_relevance.py` evaluated 3,456 configurations using only the
24 calibration queries. Eligible configurations had to reach:

- reject accuracy `1.0`;
- false-reject rate at most `0.05`.

The selected configuration is:

| Parameter | Value |
|---|---:|
| BM25 weight | 1.0 |
| Dense weight | 0.5 |
| RRF k | 10 |
| Candidate depth per channel | 50 |
| Dense accept threshold | 0.42 |
| Dense floor with BM25 evidence | 0.30 |
| BM25 evidence threshold | 20.0 |
| Fusion-margin threshold | 0.004 |

The model is `sentence-transformers/all-MiniLM-L6-v2` at revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. Document embeddings are L2-normalized,
so `IndexFlatIP` is exact cosine retrieval for this catalog.

## Held-out results

The table below uses the 24 held-out queries: 19 relevant and 5 OOD.

| Arm | Recall@5 | Recall@10 | NDCG@10 | MRR@10 | OOD reject accuracy | False-reject rate |
|---|---:|---:|---:|---:|---:|---:|
| Legacy lexical | 0.1378 | 0.2895 | 0.2854 | 0.3158 | 0.0 | 0.0 |
| BM25 | 0.4334 | 0.6847 | 0.6790 | 0.7444 | 1.0 | 0.1053 |
| Dense | **0.6492** | **0.8806** | **0.8319** | **0.8772** | 1.0 | 0.0 |
| Hybrid | 0.5966 | 0.8122 | 0.8131 | 0.8596 | 1.0 | 0.0 |

Hybrid versus the legacy lexical path:

- NDCG@10 delta: `+0.5277`, paired 95% CI `[+0.3130, +0.7257]`;
- Recall@10 delta: `+0.5227`, paired 95% CI `[+0.3122, +0.7174]`;
- MRR@10 delta: `+0.5439`, paired 95% CI `[+0.3158, +0.7544]`;
- OOD reject accuracy: `0.0 -> 1.0`.

Dense retrieval was the strongest overall held-out arm. Hybrid did not beat dense on
overall NDCG@10, and that negative result is retained. Hybrid was strongest on the
spelling/noise slice (`NDCG@10 0.8945` versus dense `0.6372`) and preserves the intended
lexical-plus-semantic product design. The predeclared rollout gate compared hybrid with
the legacy online path and passed, so `hybrid_v1` is the default while dense remains a
measured alternative.

## Runtime and artifact safety

- Artifact metadata records model revision, source fingerprint, document count,
  embedding dimension, hybrid configuration, and SHA-256 hashes.
- Online loading rejects missing files, file corruption, source-fingerprint mismatch,
  unsupported schema, or an unavailable local encoder.
- `/readyz` exposes a `search_index` dependency.
- Prometheus exposes search resolution outcomes and retrieval duration.
- BM25/dense search artifacts are separate from the existing ALS FAISS artifacts.

Warm in-process retrieval over the 174-document demo index measured p50 `6.433 ms` and
p95 `9.568 ms` over 100 calls. This excludes HTTP, MySQL, event writes, concurrency, and
production capacity.

## Reproduction

```bash
python scripts/build_search_index.py \
  --corpus full \
  --model-revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 \
  --config evaluation/search_relevance/selected_config.json

python scripts/calibrate_search_relevance.py

python scripts/eval_search_relevance.py \
  --config evaluation/search_relevance/selected_config.json

python scripts/build_search_index.py \
  --corpus demo \
  --model-revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 \
  --config evaluation/search_relevance/selected_config.json \
  --online-config evaluation/search_relevance/online_demo_config.json

python scripts/benchmark_search_retrieval.py --iterations 100
```

## Limitations

- Only 12 of 1,239 labels received a human spot-check; the remaining judgments are
  AI-assisted.
- The held-out set contains 24 queries, so confidence intervals remain wide.
- Candidate pooling reduces unjudged-document bias but cannot eliminate it.
- Full-catalog relevance and 174-document online serving are different distributions.
- The canonical `query_key` derived from top article topics is a compatibility bridge,
  not a complete semantic representation of the free-text query.
- No online search logs exist, so there is no CTR or causal validation.
