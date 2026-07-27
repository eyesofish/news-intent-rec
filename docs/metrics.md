# MIND Recommendation Metrics

Current machine-readable evidence:

- `docs/metrics/mind_recommendation.json`
- `docs/metrics/mind_intent_mechanism.json`
- `docs/metrics/mind_search_relevance.json`
- `docs/metrics/mind_search_latency.json`
- `docs/metrics/mind_system.json`

The main ranking split is a global chronological request holdout inside MIND-small
train. Requests are never divided across partitions. LightGBM trains on 20,000 complete
requests and evaluates on 10,000 complete requests using only real exposed candidates.

| Arm | Recall@5 | Recall@10 | NDCG@10 | MRR |
|---|---:|---:|---:|---:|
| Popularity | 0.3028 | 0.4831 | 0.2541 | 0.2167 |
| Category-profile manual | 0.3325 | 0.5027 | 0.2703 | 0.2334 |
| LightGBM | **0.4213** | **0.5969** | **0.3628** | **0.3293** |
| ALS-adjusted LightGBM | 0.4212 | 0.5967 | 0.3627 | 0.3292 |

ALS candidate Recall@50 is 0.0262. LightGBM exceeded the tested baselines, but ALS did
not add sampled Recall@10. Pointwise metrics are ROC AUC 0.6719, PR AUC 0.0738, and
log loss 0.1516.

Official dev known-user coverage is only 11.44%, so it is not presented as a general
known-user collaborative benchmark. The content/category fallback reached Recall@10
0.5568 on 8,902 sampled unknown-user requests.

The intent report injects deterministic category queries into three demo scenarios.
Only one scenario changed top-10 target-category share; mean delta was 0.2. MIND has no
observed search logs, so this is not a CTR, causal-lift, or user-benefit result.

Search relevance uses a fixed 48-query benchmark over all 65,238 normalized articles
with 1,239 pooled judgments. Labels are AI-assisted; 12 stratified judgments were
approved in a human spot-check.

| Search arm | Recall@10 | NDCG@10 | MRR@10 | OOD reject accuracy |
|---|---:|---:|---:|---:|
| Legacy lexical | 0.2895 | 0.2854 | 0.3158 | 0.0 |
| BM25 | 0.6847 | 0.6790 | 0.7444 | 1.0 |
| Dense | **0.8806** | **0.8319** | **0.8772** | 1.0 |
| Hybrid | 0.8122 | 0.8131 | 0.8596 | 1.0 |

Hybrid improved held-out NDCG@10 over lexical by `0.5277`; the paired 95% interval is
`[0.3130, 0.7257]`. Dense remained the strongest overall arm, while hybrid was strongest
on spelling/noise queries. See `docs/search_relevance.md` for the full protocol and
limitations.

Local measurements:

| Surface | p50 | p95 | Boundary |
|---|---:|---:|---|
| Feed API loopback | 9.47 ms | 14.18 ms | 30 local requests |
| Hybrid retrieval | 6.433 ms | 9.568 ms | 100 warm in-process calls, 174 documents |

Historical pre-migration metrics remain available in Git history and are not current.
