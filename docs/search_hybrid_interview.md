# Hybrid Search Interview Deep Dive

## Safe project claim

**Classification: code implemented, with offline evidence.**

The project replaced a `LIKE`-driven free-text path with exact aliases plus BM25,
sentence-transformer embeddings, FAISS cosine retrieval, reciprocal-rank fusion, and a
calibrated 422 rejection gate. It also built a reproducible relevance benchmark and kept
the search-to-feed intent feedback loop.

Ownership is **[主导度待确认]**. The repository proves the system behavior, not who
personally led every design decision.

## Resume bullet

> [主导度待确认] 将新闻自由文本搜索从 exact/prefix/contains/LIKE 升级为
> exact alias + BM25 + sentence-transformer/FAISS 混合检索，构建 48-query、
> 1,239 条 pooled qrels 的离线评测；在 held-out 集上将 NDCG@10 从
> 0.2854 提升至 0.8131、Recall@10 从 0.2895 提升至 0.8122，并将 OOD
> 正确拒绝率从 0 提升至 1.0，同时保留 422 拒绝语义与搜索意图反哺 Feed。

面试时必须补充：标签以 AI 辅助为主，仅有 12 条分层人工抽查；这不是 CTR 或
线上因果收益。

## 1-minute version

原来的搜索会先用 exact、prefix、contains 和文章 `LIKE` 把自由文本压成一个
topic key，再按 topic 找文章。它能运行，但对同义词、改写、拼写错误和无关
查询没有相关性证据，而且候选不足时会用热门文章补齐。我先冻结旧算法并建立
48 条查询、1,239 条 pooled qrels 的评测集，然后实现 BM25 和
all-MiniLM-L6-v2 + FAISS 两路召回，用 RRF 融合，并在 calibration split 上
校准置信度阈值。线上保留 numeric/exact alias 的高精度路径；自由文本只有在
置信度足够时才返回结果，否则 422，也不再热门补齐。held-out 上 hybrid 的
NDCG@10 从 0.2854 提升到 0.8131，OOD 拒绝率从 0 到 1.0。dense 单路整体略高，
但 hybrid 在拼写噪声 slice 最强，这个负结果和取舍都保留在报告里。

## 5-minute structure

1. **问题定义**：功能测试证明链路，不证明语义相关性。
2. **旧链路**：`query_text -> query_key -> topic lookup + LIKE + hot backfill`。
3. **评测先行**：先冻结 lexical baseline，再做固定 query split 和 candidate
   pooling，避免只展示几个成功例子。
4. **双路召回**：
   - BM25 负责关键词、实体、拼写仍可匹配的 lexical evidence；
   - MiniLM + FAISS 负责同义词和自然语言改写。
5. **融合**：选择 weighted RRF，而不是直接相加 BM25 和 cosine 分数。
6. **拒绝**：排名与“是否应该回答”分开；使用 dense evidence、BM25 evidence
   和 fusion margin 校准 422。
7. **兼容现有系统**：从高置信 article hits 聚合 topics，映射到 canonical
   `query_key`，继续写 search event 和 recent query，从而影响后续 feed。
8. **可靠性**：artifact fingerprint/hash/model revision/readiness/503，不静默
   fallback。
9. **结果**：hybrid 显著超过旧 lexical；dense 单路总体最高，hybrid 在 typo
   slice 最强。
10. **边界**：AI-assisted labels、小 query set、无真实 search log、无 CTR。

## Core code route

```text
POST /search
-> backend/app/routers/search.py::search
-> backend/app/services/search.py::SearchService.search
-> backend/app/repositories/mysql.py::MysqlRuntimeRepository.search
-> backend/app/repositories/query_resolver.py::resolve_search_query
-> backend/app/search_retrieval.py::HybridSearchIndex.search
-> backend/app/search_retrieval.py::build_hybrid_search_result
-> backend/app/repositories/content_dao.py::load_search_candidates
-> event/profile update
-> SearchResponse
```

Offline route:

```text
scripts/build_search_index.py
-> evaluation/search_relevance/queries.jsonl + qrels.jsonl
-> scripts/calibrate_search_relevance.py
-> scripts/eval_search_relevance.py
-> docs/metrics/mind_search_relevance.json
```

## Three-layer questions

### 1. Why not use embeddings only?

**Layer 1:** Dense retrieval handles semantic rewrites but can miss rare tokens,
misspellings, and exact entities. BM25 adds explicit lexical evidence.

**Layer 2:** On this benchmark, dense was strongest overall, while hybrid was strongest
on the spelling/noise slice. The correct claim is not “hybrid always wins”; it is that
the channels have complementary failure modes.

**Layer 3:** If the traffic mix shifts away from noisy/entity queries, the extra BM25
channel may not justify its complexity. The retained dense arm and evaluation harness
make that decision measurable.

### 2. Why RRF instead of score normalization?

BM25 and cosine have unrelated score distributions. RRF uses rank positions and avoids
assuming the raw scores are calibrated. The trade-off is that it discards some score
magnitude information and introduces `k` and channel weights.

### 3. Why is rejection separate from ranking?

A ranker always produces a top result, even for an unrelated query. Returning that item
would turn “best among bad candidates” into a false success. The system therefore uses
channel evidence and calibrated thresholds before allowing the ranked list to become a
successful search response.

### 4. Why keep exact aliases?

Exact aliases are curated, deterministic, cheap, and high precision. Sending them
through embeddings can only add latency and ambiguity. Prefix/contains aliases are not
kept in the hybrid short path because they are more likely to steal a semantic query.

### 5. How does free text still affect the feed?

Hybrid retrieval returns article IDs. The resolver aggregates topics from top hits,
weights subcategories slightly more, and chooses an existing `query_topic_map` key.
That key is stored in the existing event/profile path. This preserves compatibility but
is lossy; it is not presented as a full query embedding profile.

### 6. What happens when artifacts are stale or missing?

The loader validates schema, source fingerprint, ID map, file hashes, model ID/revision,
and index row count. A configured hybrid deployment fails readiness and returns 503;
it does not silently pretend lexical fallback is the requested hybrid service.

## Most likely weak points

- The qrels are not a large human-gold benchmark.
- Only 24 queries are held out.
- Dense was better than hybrid overall.
- Full-catalog evaluation and demo serving have different corpus sizes.
- The query-key compatibility bridge collapses richer semantic intent.
- No production concurrency, memory, or API latency benchmark was run.

## Can write / do not write

| Can write | Do not write |
|---|---|
| BM25 + sentence-transformer + FAISS hybrid retrieval | Production-grade search platform |
| Reproducible offline relevance evaluation | Online CTR improvement |
| Held-out NDCG/Recall/MRR on the fixed labeled set | Human-gold benchmark |
| Calibrated low-confidence rejection | Perfect semantic understanding |
| Artifact fingerprint/hash/readiness governance | Vector database or distributed search |
| Honest dense-vs-hybrid ablation | Hybrid was the best arm overall |

## Best concise defense

> 我不是先把 embedding 接进接口再找几个好例子，而是先冻结旧 lexical baseline，
> 再用同一批 query/qrels 比较 lexical、BM25、dense 和 hybrid。最终 hybrid
> 显著超过旧线上路径，并在 typo/noise slice 最强；dense 单路总体略高，这个
> 负结果我也保留。上线时我用预先冻结的 gate 决定默认策略，同时用 422 和
> readiness 保护低置信度与 artifact 故障。
