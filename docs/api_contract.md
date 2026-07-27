# NewsIntentRec API Contract

Public content fields are `article_id`, `headline`, `abstract`, `source_domain`, and
`categories`. The MySQL compatibility schema still uses answer/question table names;
those names are not exposed by OpenAPI.

## Main routes

- `GET /feed`
- `POST /search`
- `GET /articles/{article_id}`
- `POST /event/track`
- `POST /event/recommendation_click`
- `POST /event/search_result_click`
- `GET /personas`
- `GET /debug/profile`
- `GET /livez`, `/readyz`, `/healthz`, `/metrics`

Feed and search items use:

```json
{
  "article_id": 123,
  "headline": "Real MIND headline",
  "abstract": "Real MIND abstract",
  "source_domain": "msn.com",
  "categories": [{"topic_id": 1, "display_name": "news"}]
}
```

`GET /feed` accepts `user_id`, `page_size`, `debug`, `request_id`,
`include_sponsored`, `experiment_arm`, and the evaluation-only `as_of_ts`.

`POST /search` accepts either a normalized `query_key` or English `query_text`.
Numeric keys and exact category/subcategory aliases use the deterministic topic path.
Other free text uses BM25 plus sentence-transformer/FAISS retrieval and weighted RRF.
Only high-confidence candidates are returned; search never fills a short page with hot
articles. Low-confidence input returns 422 `unresolved_query`. Missing, corrupt, stale,
or locally unavailable hybrid artifacts return 503 `search_index_not_ready`.

Search score fields are `topic_match_score`, `bm25_score`, `dense_score`,
`hybrid_score`, and `final_score`. Debug output includes retrieval mode, resolution
source/confidence, result provenance, matched topics, and model artifact identity.

Unified product events use:

```json
{
  "event_id": "client-idempotency-key",
  "user_id": 42,
  "event_type": "feed_impression",
  "surface": "feed",
  "article_id": 123,
  "request_id": "feed-request"
}
```

Article events require `article_id`; search-result clicks also require `query_key`, and
`dwell` requires bounded `dwell_ms`. Kafka user and training messages use schema
version 3. Consumers retain an internal schema-v2 migration shim so already-staged
legacy content-ID messages can drain without changing idempotency fingerprints.

Sponsored cards use the same article fields and add a labeled `sponsored` object.
Sponsored IDs are validated server-side against MySQL rather than trusted from clients.
