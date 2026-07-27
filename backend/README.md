# NewsIntentRec Backend

FastAPI logical monolith for article feed/search serving, event ingestion, profile
state, sponsored delivery, health, and observability.

- MySQL is the online source of truth.
- `MysqlRuntimeRepository` uses the legacy answer/question tables only as a migration
  compatibility layer; public schemas expose article/news fields.
- `sync_mysql`, `kafka_dual_write`, and `kafka_async` event modes share idempotent
  event identities and durable Outbox semantics.
- Kafka user/training messages use schema v3 `article_id`; consumers can drain staged
  schema-v2 content-ID messages.
- LightGBM and ALS artifacts under `build/mind_models` are optional and
  schema/fingerprint validated.
- Hybrid search artifacts under `build/mind_search/demo` contain BM25 corpus data,
  normalized MiniLM embeddings, a FAISS index, model revision, hashes, and the selected
  rejection/fusion configuration.

Main API groups:

- recommendation: `/feed`;
- search: `/search`, `/search/suggestions`;
- product content: `/personas`, `/articles/{article_id}`;
- events: `/event/track` and click endpoints;
- debugging: `/debug/profile`;
- system: `/livez`, `/readyz`, `/healthz`, `/metrics`.

```bash
export NEWSREC_DATABASE_URL='mysql+pymysql://root:root@127.0.0.1:3306/newsrec_demo'
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

See `docs/local_runbook.md` for the full stack.
