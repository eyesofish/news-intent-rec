# NewsIntentRec

Personal news recommendation system built with the **public Microsoft MIND dataset**.
This is not a Microsoft product or internship deliverable, and it does not use
Microsoft-internal data, code, models, or infrastructure.

MIND provides real article impressions, exposed non-clicks, clicks, and pre-request
history. It does **not** provide user search logs. Search in this project is a local
product feedback mechanism; `docs/metrics/mind_intent_mechanism.json` demonstrates
mechanism behavior only and is not evidence of CTR or causal user benefit.

## What is implemented

- deterministic MIND download/inspection/normalization with checksums and fingerprints;
- real impression-aware negatives and request-level chronological evaluation;
- ALS + FAISS collaborative recall with explicit unknown-user fallback;
- LightGBM ranking, popularity/category baselines, and honest negative/positive ablations;
- exact-alias + BM25 + sentence-transformer/FAISS hybrid search with calibrated rejection;
- FastAPI + MySQL serving, Outbox/Kafka, idempotent consumers, health and metrics;
- React feed/search, source/category labels, personas, and explanations;
- separate full-data model evidence and compact deterministic serving/CI worlds.

## Current evidence

Normalized fingerprint:
`643c53b0ce5fddf5e08a8d6f8e491ddec607a3f56c335c44d872e6e74cbd4b52`.

The ranking report uses a global chronological holdout inside MIND-small train.
LightGBM uses 20,000 complete train requests and 10,000 complete evaluation requests.

| Arm | Recall@10 | NDCG@10 | MRR |
|---|---:|---:|---:|
| Popularity | 0.4831 | 0.2541 | 0.2167 |
| Category-profile manual | 0.5027 | 0.2703 | 0.2334 |
| LightGBM | **0.5969** | **0.3628** | **0.3293** |
| ALS-adjusted LightGBM | 0.5967 | 0.3627 | 0.3292 |

ALS did not add sampled Recall@10 beyond LightGBM. Its all-catalog candidate Recall@50
was 0.0262, so the project retains that negative result. Official dev known-user
coverage is 11.44%; unknown-user content/category fallback Recall@10 was 0.5568 on
8,902 sampled cold-start requests.

Search relevance uses 48 fixed queries and 1,239 pooled judgments over all 65,238
normalized articles. Labels are AI-assisted with a user-approved 12-row stratified
spot-check.

| Search arm | Recall@10 | NDCG@10 | MRR@10 | OOD reject accuracy |
|---|---:|---:|---:|---:|
| Legacy lexical | 0.2895 | 0.2854 | 0.3158 | 0.0 |
| BM25 | 0.6847 | 0.6790 | 0.7444 | 1.0 |
| Dense | **0.8806** | **0.8319** | **0.8772** | 1.0 |
| Hybrid | 0.8122 | 0.8131 | 0.8596 | 1.0 |

Hybrid is the default because it passed the frozen rollout gate and was strongest on
spelling/noise queries. Dense was the strongest overall held-out arm; that negative
result is retained rather than hidden.

The existing feed loopback measurement was p50/p95 9.47/14.18 ms. Warm in-process
hybrid retrieval over the 174-document demo index measured 6.433/9.568 ms. These are
local measurements, not production capacity claims.

## Data setup

Read the [Microsoft Research License Terms](https://github.com/msnews/MIND/blob/master/MSR%20License_Data.pdf).
The official MIND page currently routes downloads through gated Hugging Face access.
The downloader requires explicit acceptance and supports either that source or the
explicitly selected public raw-file mirror:

```bash
python scripts/download_mind.py --variant small --split all --accept-license --source huyva
python scripts/inspect_mind.py --variant small
python scripts/normalize_mind.py
python scripts/build_mind_demo_world.py
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
python scripts/import_demo_world.py \
  --input-dir build/mind_demo_world \
  --output-sql build/mind_demo_world/import_demo_world.sql \
  --truncate-first
python scripts/train_eval_mind.py
```

Raw MIND files, normalized Parquet, demo packs, and model binaries remain local and are
not committed.

## Local bootstrap

```bash
python -m pip install -r backend/requirements-dev.txt
PYTHON=.venv/bin/python scripts/init_local.sh --product-frontend
```

Add `--smoke-test` for a one-shot check or `--with-kafka` for Kafka workers.
The default database is `newsrec_demo`, seed directory is `build/mind_demo_world`, and
the public API uses article fields and `/articles/{article_id}`.

## Development gates

```bash
python -m ruff check backend scripts tests
python -m mypy
python -m pytest -q

cd product-frontend
npm ci
npm test -- --run
npm run build
```

MySQL and Kafka integration jobs run in `.github/workflows/ci.yml`.

## Documentation

| Topic | Document |
|---|---|
| Data inspection and ALS split decision | `docs/mind_data_inspection.md` |
| Aggregate data analysis | `docs/data_analysis_report.md` |
| Recommendation metrics | `docs/metrics.md` |
| Machine-readable recommendation evidence | `docs/metrics/mind_recommendation.json` |
| Search mechanism evidence | `docs/metrics/mind_intent_mechanism.json` |
| Search relevance evaluation | `docs/search_relevance.md` |
| Machine-readable search evidence | `docs/metrics/mind_search_relevance.json` |
| Hybrid search interview deep dive | `docs/search_hybrid_interview.md` |
| API and event contract | `docs/api_contract.md` |
| Local operations | `docs/local_runbook.md` |
| Product/HCI walkthrough | `docs/hci_report.md` |
| Migration plan | `plan/mind_migration_plan_zh.md` |
