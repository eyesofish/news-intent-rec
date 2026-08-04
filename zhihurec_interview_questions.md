# NewsIntentRec（目录名 zhihurec）带读笔记

> **目标：3 天内达到“面试追问不露馅”**。不背框架语法，重点掌握数据语义、离线评估、召回排序、搜索反馈、事务幂等和系统边界。  
> **当前版本基线：公开 MIND 新闻数据**。旧 ZhihuRec 指标和旧文件路径已经失效，不再作为当前项目证据。  
> **三天路线**：Day 1 读 §1–§3；Day 2 读 §4–§7；Day 3 读 §8–§9，并完成 90 秒项目讲述。  
> **使用规则**：每轮只完成一个 checkbox；先猜，再解释；所有结论必须能落回具体代码和当前证据。

## 0. 面试口径红线

- 当前最强排序 arm 是 LightGBM：Recall@10 `0.5969`；ALS-adjusted LightGBM 为 `0.5967`，不能说 ALS 带来了提升（`docs/metrics.md:13`）。
- ALS all-catalog candidate Recall@50 只有 `0.0262`，应作为负结果诚实解释（`docs/metrics.md:20`）。
- official dev known-user coverage 只有 `11.44%`；unknown-user content/category fallback Recall@10 为 `0.5568`（`docs/metrics.md:24`）。
- MIND 没有搜索日志；搜索实验只是 deterministic intent mechanism evidence，不能声称 CTR、因果提升或用户收益（`docs/metrics.md:29`）。
- article age 使用“首次出现在所选 impression 窗口”的时间，不是新闻发布时间（`docs/mind_data_inspection.md:45`）。
- feed/search 延迟只是本地 loopback 30 次测量，不能包装成生产容量（`README.md:42`）。

## 1. Day 1 热身：请求入口、分层与产品契约

1. ⭐ `app = create_app()` 为什么在 import 时就创建应用？
    - [x] **前置 1.P1** 看懂模块顶层语句会在 `uvicorn backend.app.main:app` 导入时执行（`backend/app/main.py:207`）。
    - [x] **主问 1.Q1** 从 `@router.get("/feed")` 追到 `FeedService.get_feed()`，再追到 repository（`backend/app/routers/feed.py:12`，`backend/app/services/feed.py:11`）。
2. ⭐ `Depends(get_feed_service)` 注入的值来自哪里？
    - [x] **前置 1.P2** 看懂 `service` 不是前端参数，而是 FastAPI 调用 provider 得到的对象（`backend/app/routers/feed.py:36`）。
    - [x] **主问 1.Q2** 解释 `get_runtime_repository()` 如何按数据库配置选择 MySQL 或 Unwired 实现（`backend/app/dependencies.py:21`，`backend/app/dependencies.py:28`）。
3. ⭐ 为什么 Service 层很薄，却仍然保留？
    - [x] **前置 1.P3** 看懂 `FeedService` 只保存 `_repository` 并转发参数（`backend/app/services/feed.py:7`）。
    - [x] **主问 1.Q3** 说明薄 Service 对依赖替换、测试和未来业务编排的收益，以及当前多一层跳转的成本。
4. ⭐ 为什么产品 API 叫 `article_id`，数据库代码里仍大量出现 `answer_id`？
    - [x] **前置 1.P4** 对比 `FeedItem.article_id` 与 `load_answer_rows()` 的内部兼容命名（`backend/app/schemas/feed.py:40`，`backend/app/repositories/content_dao.py:200`）。
    - [x] **主问 1.Q4** 解释“先稳定产品契约、暂不高风险重命名底层表”的迁移 trade-off（`docs/api_contract.md:1`）。
5. ⭐ 为什么数据库未配置时返回 503，而不是空 feed？
    - [x] **前置 1.P5** 看懂 `UnwiredRuntimeRepository.get_feed()` 主动抛出 `RepositoryNotReadyError`（`backend/app/repositories/unwired.py:29`）。
    - [x] **主问 1.Q5** 解释 success-shaped empty response 会怎样掩盖部署故障，以及 `response_model` 如何稳定正常响应契约（`backend/app/main.py:121`，`backend/app/routers/feed.py:12`）。
6. ⭐ 整个库一共几张表，`/feed` 这一条请求链路实际摸到哪几张？
    - [x] **前置 1.P6** 数一遍 `sql/schema.sql` 的 21 张 `CREATE TABLE`，按角色分组：内容本体（`topic`/`author`/`question`/`answer`/`question_topic`/`answer_topic`）、用户与画像（`app_user`/`user_profile`/`system_profile_seed`）、召回辅助（`query_topic_map`/`hot_answer_snapshot`）、广告（`sponsored_campaign`/`sponsored_campaign_topic`/`sponsored_creative`/`sponsored_campaign_daily_state`/`sponsored_user_daily_frequency`/`sponsored_delivery`）、幂等与事件基础设施（`feed_request`/`event_idempotency`/`user_event`/`event_outbox`/`worker_heartbeat`）。
    - [x] **主问 1.Q6** 结合代码里实际的 `FROM`/`JOIN` 证据（`content_dao.py`、`profile_dao.py`、`sponsored_dao.py`），说清楚 `get_feed()` 真正碰到的表只是这 21 张里的一个子集——`app_user` 只作外键约束、并不会被 `/feed` 查询（它是 `list_personas()` 调试接口在查）；ALS 召回压根不经过 MySQL，是直接读磁盘上的 `.npy`/FAISS 文件。说明"最核心、缺一不可"的是 `answer`+`answer_topic`/`topic`+`user_profile`/`system_profile_seed`+`feed_request` 这四类，并解释它们之间"个性化匹配"是在 Python 里用字典交集算的，不是一条 SQL JOIN（因为 `topic_weights_json` 是 JSON 字段，直接 JOIN 效率不划算）。

> 带读笔记（已讨论）
>
> - 当前理解：`backend.app.main` 被导入时，Python 会执行模块顶层的 `app = create_app()`，因此 Uvicorn 随后能从模块中取得已创建的 `app` 对象。
> - 可复用模式 / trade-off：模块级应用对象符合 ASGI 服务器的 `module:attribute` 加载约定，启动简单；代价是导入模块会产生创建应用的副作用。
> - 关于 feed 调用链的当前理解：FastAPI router 接收并校验 HTTP 参数，调用 `FeedService.get_feed()`；Service 保持业务入口，再把请求委托给注入的 `RuntimeRepository` 具体实现。
> - 可复用模式：用 Router → Service → Repository 分离传输协议、业务编排和数据访问，使每层可以独立替换与测试。
> - trade-off：当前 Service 很薄，会增加一次跳转；但为未来跨 repository 编排与统一业务策略保留稳定入口。
> - 关于 FastAPI 注入的当前理解：`service` 不是客户端请求字段；FastAPI 解析 `Depends(get_feed_service)` 后在服务端调用 provider，并把返回的 `FeedService` 作为函数参数。
> - 可复用模式：路由声明需要什么依赖，不在函数内部手工构造，测试可覆盖 provider 或注入替身。
> - trade-off：依赖注入减少耦合，但对象来源变得隐式，排查时必须沿 `Depends` 追到 provider。
> - 关于 repository 选择的当前理解：`get_runtime_repository()` 读取 settings；配置数据库时构造 MySQL 实现，否则构造显式不可用的 Unwired 实现，并通过缓存复用该实例。
> - 可复用模式：上层依赖稳定的 Repository 协议，运行时 provider 根据环境选择实现。
> - trade-off：集中选择逻辑避免各路由分支判断；缓存长生命周期连接池更高效，但测试改配置时需清理 cache。
> - 关于薄 Service 的当前理解：`FeedService` 构造时只保存符合 `RuntimeRepository` 协议的 `_repository`，`get_feed()` 当前原样转发参数和响应。
> - 可复用模式：即使初期没有复杂业务，也可先建立稳定的业务入口，避免 Router 直接绑定具体数据实现。
> - trade-off：当前多一层跳转看似冗余，价值主要体现在替换依赖、测试和未来编排。
> - 关于保留薄 Service 的当前理解：它让 Router 不依赖具体 repository，测试可注入 fake，未来权限、实验、广告或多仓库编排可集中在业务层；当前成本是额外跳转与样板。
> - 可复用模式：是否保留抽象层要看它是否形成稳定变化边界，而不是用当前代码行数判断。
> - trade-off：过早堆叠无演进方向的层会增加认知成本；这里已有多 repository 与多业务入口，因此边界有现实用途。
> - 关于内容 ID 命名的当前理解：公共 Pydantic/API 契约统一使用 `article_id`；repository 与 MySQL 兼容层仍从旧 `answer.answer_id` 读取，并在组装响应时映射为产品语义。
> - 可复用模式：外部契约与内部存储命名可以通过适配边界解耦，不必要求迁移在同一天完成。
> - trade-off：兼容层降低大规模重命名风险，但双重术语会增加维护认知成本，需要明确禁止旧名泄漏到 OpenAPI。
> - 关于分阶段迁移的当前理解：先把公共 API、事件和产品术语稳定为 `article_id`，通过 repository 适配旧 schema；底层表重命名作为独立高风险迁移另行验证。
> - 可复用模式：优先切断错误抽象继续向外扩散，再在受控边界后逐步偿还内部命名债务。
> - trade-off：短期保留双语适配增加认知负担，但避免一次变更同时触碰客户端、数据库和历史消息。
> - 关于 Unwired repository 的当前理解：数据库未配置时仍提供同一 Repository 接口，但各业务方法主动抛出带 operation 的 `RepositoryNotReadyError`，不伪造成功数据。
> - 可复用模式：不可用实现也应遵守接口，并用明确失败语义暴露部署缺口。
> - trade-off：应用进程仍可启动并提供 health/error 信息，但业务请求会失败；这比启动即崩溃更可诊断，也比空响应更诚实。
> - 关于失败与成功契约的当前理解：repository 未就绪由全局 handler 返回 503 与 `repository_not_ready`；正常 `/feed` 响应始终经 `FeedResponse` 校验，空结果也必须是合法业务响应而非故障伪装。
> - 可复用模式：HTTP 状态表达操作是否成功，response schema 表达成功数据形状，两者不能互相替代。
> - trade-off：显式 503 要求客户端处理错误路径，但能让监控、重试和运维正确识别配置故障。
> - **【复习 Round 2 薄弱点】1.P1**：误以为 `app = create_app()` 是收到第一个 HTTP 请求时才执行，实际是 `import backend.app.main` 这一刻、模块顶层语句就顺序执行了（`backend/app/main.py:207`）。需要巩固：Python 模块导入 = 从上到下跑一遍脚本，不是只注册函数/类声明。
> - **【复习 Round 2 薄弱点】1.Q1**：误以为"去掉 Service 层、Router 直接调 Repository"会导致运行时报错（HTTP 500）。实际上 Python/FastAPI 不会在运行时强制检查分层，技术上完全跑得通、不报错；真正的代价是架构层面的——失去统一业务入口，未来跨 repository 编排/权限/实验分流逻辑无处收敛，只能散落进各 Router。分层是约定，不是运行时机制。
> - 关于全库表结构的当前理解：`sql/schema.sql` 共 21 张表，按角色分内容本体、用户画像、召回辅助、广告、幂等与事件基础设施五组；`/feed` 这一条请求链路实际只碰其中一个子集——`feed_request`/`user_profile`/`system_profile_seed`/`query_topic_map`/`answer`/`answer_topic`/`hot_answer_snapshot`/`user_event`（只读），以及 JOIN 带出的 `topic`/`author`/`question` 展示字段；开启广告再加 `sponsored_*` 一串。`app_user` 只作外键约束，`/feed` 本身不查它；ALS 召回不经过 MySQL，读的是磁盘上的 `.npy`/FAISS 文件。
> - 可复用模式：最核心、缺一不可的是 `answer`（有什么可推荐）+`answer_topic`/`topic`（内容的话题标签）+`user_profile`/`system_profile_seed`（这个人/这类人喜欢什么）+`feed_request`（防重复处理）四类；其余是叠加在核心链路上的增强层（热门兜底、搜索信号、广告）。个性化匹配（用户话题权重 vs 文章话题集合）是查出来后在 Python 里用字典/集合做交集计算的，不是一条 SQL JOIN——因为话题权重存在 JSON 字段里，MySQL 对 JSON 做关联开销更高，不如各查一次、搬到应用层用字典匹配。
> - trade-off：把匹配逻辑放到应用层，减少了数据库端复杂 JOIN 的负担，但要求应用层自己保证候选数量可控（`candidate_limit` 封顶），否则大量候选在 Python 里做匹配也会变慢。
> - 还没展开的问题：§1 已完成；进入 2.P2，理解跨 split 的 request ID namespace。

## 2. Day 1：MIND 数据语义与确定性归一化

1. ⭐ `N123-0` 里的 `0` 到底是什么负样本？
    - [x] **前置 2.P1** 看懂 `parse_candidate()` 如何拆出 article ID 和 click label（`backend/app/data_contracts/mind.py:111`）。
    - [x] **主问 2.Q1** 解释 exposed non-click 与“随机抽一个没点过的 article 当负样本”的本质区别。
2. ⭐ 为什么 request ID 必须带 split？
    - [x] **前置 2.P2** 看懂 `request_id=f"mind:{split}:{impression_id}"`（`backend/app/data_contracts/mind.py:139`）。
    - [x] **主问 2.Q2** 结合 train/dev 原始 impression ID 会重叠，解释不加 namespace 会造成什么碰撞（`docs/mind_data_inspection.md:21`）。
3. ⭐ 为什么归一化阶段要拒绝“没有 metadata 的候选”？
    - [x] **前置 2.P3** 看懂 `scan_requests()` 同时校验 history 和 candidates 的 article ID（`scripts/normalize_mind.py:148`）。
    - [x] **主问 2.Q3** 推演 orphan candidate 进入训练、在线内容表和评估后会分别造成什么错误（`tests/test_normalize_mind.py:83`）。
4. ⭐ topic ID 为什么来自排序后的字符串，而不是 Python `hash()`？
    - [x] **前置 2.P4** 看懂 `build_topic_maps()` 对 category/subcategory key 排序后编号（`scripts/normalize_mind.py:198`）。
    - [x] **主问 2.Q4** 解释稳定 ID 对重复构建、模型 artifact 和数据库 import 的意义。
5. ⭐ normalized fingerprint 能证明什么，不能证明什么？
    - [x] **前置 2.P5** 看懂 output hashes 如何合成 `normalized_fingerprint`（`scripts/normalize_mind.py:355`）。
    - [x] **主问 2.Q5** 区分“输入输出可复现”与“模型效果正确”，并解释 provenance 为什么单独记录时间和负样本语义（`scripts/normalize_mind.py:365`）。

> 带读笔记（已讨论）
>
> - 当前理解：`parse_candidate("N123-0")` 得到 `clicked=False`；该负样本代表真实曝光后未点击，而不是从全库随便抽到的未点击内容。
> - 可复用模式 / trade-off：曝光负样本更贴近线上同屏竞争、通常更难；随机负样本易获取，但可能过于简单，使离线指标虚高并造成训练/服务分布偏移。
> - 关于 request namespace 的当前理解：canonical ID 使用 `mind:{split}:{impression_id}`；因为 train/dev 原始 impression ID 会重叠，split 是请求身份的一部分。
> - 可复用模式：合并多个各自局部唯一的数据源时，先把来源 namespace 纳入主键，再做 join、分组和去重。
> - trade-off：复合 ID 更长，但能避免静默碰撞；随机 UUID 虽唯一，却会破坏重复构建的稳定性。
> - 关于碰撞风险的当前理解：若省略 split，不同请求会在主键、候选分组、label join 和 request-level 指标中被误合并，形成难以察觉的数据污染。
> - 关于 metadata coverage 的当前理解：归一化扫描要求 history 与 candidates 中每个 article ID 都能在 news metadata 找到；未点击候选也不能例外。
> - 可复用模式：在数据入口尽早验证跨文件引用完整性，避免 orphan key 流入更下游才以缺特征或缺内容形式爆炸。
> - trade-off：fail fast 会拒绝部分可勉强使用的数据，但比静默补默认内容更能保护训练与 serving 契约。
> - 关于 orphan candidate 的当前理解：它会让训练特征 join 缺失、线上内容表无法渲染，并让评估包含模型不可服务的样本；因此归一化直接报 `lacks metadata`。
> - 可复用模式：数据质量规则应覆盖训练、serving、evaluation 的共同可服务集合，不能只保证某一个脚本能跑。
> - trade-off：拒绝 orphan 会减少数据量，但保留它会制造指标与产品能力不一致的虚假样本。
> - 关于 topic ID 构建的当前理解：先生成带层级前缀的 category/subcategory key 集合，字典序排序后从 1 编号，因此相同输入集合得到相同映射。
> - 可复用模式：持久化标识应由 canonical key 与确定性排序产生，不能依赖进程 hash 或遍历顺序。
> - trade-off：新增一个排序更靠前的 key 会让后续整数整体漂移；生产增量系统通常需持久化注册表，本项目适用于全量确定性重建。
> - 关于稳定 ID 价值的当前理解：离线 artifact、归一化 Parquet 和 MySQL import 对同一整数必须保持同一 topic 语义，否则系统会无报错地把权重应用到错误主题。
> - 可复用模式：跨组件共享整数 ID 时，映射本身也是版本化数据契约，应与 artifact 一起保存和校验。
> - trade-off：确定性重建适合固定数据集；持续新增实体时还需避免旧 ID 被重新编号。
> - 关于 normalized fingerprint 的当前理解：先计算六个归一化输出文件各自的 SHA256，再对按 key 排序序列化后的 hash 映射做总 SHA256，得到整套 artifact 身份。
> - 可复用模式：Merkle-like 汇总 hash 能用单一标识绑定多文件输出，同时保留单文件 hash 便于定位差异。
> - trade-off：fingerprint 能证明字节一致或变化，不能证明转换逻辑在业务语义上正确。
> - 关于 fingerprint 证据边界的当前理解：它证明整套输出字节是否一致，不证明业务规则或模型效果正确；规则需靠契约测试与评估验证。
> - 关于 provenance 的当前理解：manifest 单独记录 UTC 假设、first-seen 用途、history、曝光负样本和 request namespace，使数字背后的语义可审计。
> - 可复用模式：artifact identity、自动化 correctness tests、人工可读 provenance 是三类互补证据，不能互相替代。
> - trade-off：记录语义增加维护工作，但能防止后续训练者用同一数据做出错误解释。
> - 还没展开的问题：§2 已完成；检查全局 checkbox 后进入综合高压演练。

## 3. Day 1：时间切分、特征泄漏与指标

1. ⭐ 为什么 `_request_split()` 按全局时间切 request，而不是随机切 item？
    - [x] **前置 3.P1** 看懂 cutoff timestamp 前后如何形成 train/test（`scripts/train_eval_mind.py:35`）。
    - [x] **主问 3.Q1** 解释同一 request 或同一 timestamp 被拆开会怎样引入不真实的未来信息（`tests/test_train_eval_mind.py:11`）。
2. ⭐ hotness 特征为什么只能看当前 request 之前的计数？
    - [x] **前置 3.P2** 看懂先记录 `prior_impressions` / `prior_clicks`，再在 `update_counts` 时更新（`scripts/train_eval_mind.py:130`，`scripts/train_eval_mind.py:138`）。
    - [x] **主问 3.Q2** 解释如果先把当前 click 加进计数，模型会如何“偷看答案”（`tests/test_train_eval_mind.py:28`）。
3. ⭐ `article_age_hours` 的起点为什么是 `first_seen_train_ts`？
    - [x] **前置 3.P3** 看懂 age 由 request time 减 first-seen time 得到（`scripts/train_eval_mind.py:148`）。
    - [x] **主问 3.Q3** 说明为什么它只能叫数据窗口内 age，不能说 publication age。
4. ⭐ Recall@K、NDCG@K、MRR 分别惩罚什么？
    - [x] **前置 3.P4** 看懂 `_ranking_metrics()` 按 `request_id` 分组后计算指标（`scripts/train_eval_mind.py:291`）。
    - [x] **主问 3.Q4** 用“找全 / 排前 / 首中 / 不单一”区分 Recall@K、NDCG@K、MRR 和 Category Diversity@K，并解释指标冲突。
5. ⭐ 当前实验最诚实的一句话结论是什么？
    - [x] **前置 3.P5** 记住 LightGBM `0.5969`、ALS-adjusted `0.5967`、ALS Recall@50 `0.0262`（`docs/metrics.md:13`，`docs/metrics.md:20`）。
    - [x] **主问 3.Q5** 组织一句不夸大的回答：排序模型超过已测 baseline，但 ALS 没有带来可测增益，official dev 主要是冷启动面。

> 带读笔记（已讨论）
>
> - 当前理解：LightGBM 超过已测 popularity/category baseline；ALS 当前没有可测增益且候选召回偏弱；official dev 以未知用户为主，因此保留内容/类目 fallback。
> - 可复用模式 / trade-off：面试结论应同时讲正结果、负结果和适用边界；离线排序提升不能外推为线上 CTR 或所有用户上的协同收益。
> - 关于 `article_age_hours` 的当前理解：它由当前请求的 `event_ts` 减文章的 `first_seen_train_ts` 得到，秒级差值换算成小时；缺失或异常负值按 `0` 处理。
> - 可复用模式：时间特征只使用事件发生时已经可观察的时间点，并明确记录时间戳单位和起点来源。
> - trade-off：first-seen 是时间安全、可复现的年龄代理，但它依赖数据窗口，通常会低估文章真实存在时长。
> - 关于 age 命名边界的当前理解：MIND 文章 metadata 没有发布时间；`first_seen_train_ts` 是 normalizer 从训练曝光中取到的最早请求时间，只能证明“最早在此时观察到”，不能证明“在此时发布”。
> - 可复用模式：代理特征的命名必须反映可观测来源，避免把 first-seen、ingestion time 或 crawl time 包装成真实 creation time。
> - trade-off：数据窗口 age 可复现且不会引入窗口外信息，但会受观察窗口截断影响，不能跨数据集直接比较。
> - 还没展开的问题：继续沿离线训练链路理解特征表如何进入 LightGBM。

## 4. Day 2：ALS、FAISS 与协同召回

1. ⭐ ALS 训练矩阵里的一行、一列、一个非零值分别代表什么？
    - [x] **前置 4.P1** 看懂 `_train_als()` 如何把 clicked rows 变成 user-item CSR matrix（`scripts/train_eval_mind.py:185`）。
    - [x] **主问 4.Q1** 解释这里把点击作为 implicit positive 的好处，以及没有 confidence weighting 的局限。
2. ⭐ 为什么这里必须说 inner product，不能说 cosine？
    - [x] **前置 4.P2** 看懂 FAISS 使用 `IndexFlatIP`（`scripts/train_eval_mind.py:223`）。
    - [x] **主问 4.Q2** 结合代码没有 L2 normalize，解释 inner product 与 cosine 的区别（`tests/test_als_recall.py:11`）。
3. ⭐ 在线 ALS 为什么要等所有 artifact 齐全才加载？
    - [x] **前置 4.P3** 看懂 `_ensure_loaded()` 检查 index、embedding、ID map 和 metadata（`backend/app/repositories/als_recall.py:34`）。
    - [x] **主问 4.Q3** 解释只更新部分 artifact 会造成怎样的 index/ID 错位，以及 mtime signature 解决什么问题。
4. ⭐ 冷用户为什么返回 `[]`，而不是伪造一个平均向量？
    - [x] **前置 4.P4** 看懂 `get_candidates()` 在模型未加载或 user 不在 map 时直接返回空列表（`backend/app/repositories/als_recall.py:73`）。
    - [x] **主问 4.Q4** 解释“明确无协同候选 + 交给内容/热门兜底”为什么比 success-shaped fake vector 更诚实。
5. ⭐ ALS Recall@50 只有 `0.0262`，为什么代码还保留 ALS channel？
    - [x] **前置 4.P5** 看懂 `_candidate_recall()` 如何只对 known-user request 计算 all-catalog recall（`scripts/train_eval_mind.py:346`）。
    - [x] **主问 4.Q5** 从研究价值、可插拔架构和生产复杂度三方面说明保留或下线 ALS 的条件。

> 带读笔记（已讨论）
>
> - 当前理解：冷用户或模型未加载时，ALS 返回 `[]`；热门/内容候选由明确的 fallback channel 提供，而不是用平均用户向量伪造协同个性化。
> - 可复用模式 / trade-off：显式缺席保护候选 provenance、解释性和权重控制，也避免把 popularity bias 隐藏在 ALS 分数里。
> - 关于 candidate recall 的当前理解：`mean(recalls)` 只统计 ALS 已知用户且存在正例的请求，并对逐请求 Recall@K 取平均；冷用户不进入该均值。
> - 可复用模式：报告过滤后指标时，应同时报告 `coverage`，避免把小范围有效包装成全量有效。
> - trade-off：known-user 指标能隔离协同召回能力，但会排除冷用户，因此不能单独代表全量流量表现。
> - 关于 ALS 去留的当前理解：当前低 candidate recall 且没有总指标增益，不支持默认开启；“已经写完”属于沉没成本，不是保留理由。
> - 可复用模式：弱实验能力应放在可关闭通道后，并预先定义增益、覆盖率、稳定性和维护成本的 go/no-go 门槛。
> - trade-off：暂留能保留研究与迭代价值，但要承担 FAISS、模型 artifact 一致性、内存和监控成本；长期不达标应下线。
> - 还没展开的问题：进入 5.P1，理解多路候选为什么按 `article_id` 放入同一个字典。

## 5. Day 2：多源召回与冷启动混合

1. ⭐ 为什么候选容器是 `dict[article_id, candidate]`？
    - [x] **前置 5.P1** 看懂 `_load_feed_candidates()` 初始化 `candidates`（`backend/app/repositories/mysql.py:1392`，`backend/app/repositories/mysql.py:1402`）。
    - [x] **主问 5.Q1** 解释 `add_feed_candidate()` 如何去重、保留多来源并取更高 raw score（`backend/app/repositories/_utils.py:99`）。
2. ⭐ `profile_topic_ids` 和 `query_topic_ids` 分别从哪里来？
    - [x] **前置 5.P2** 看懂两组 topic ID 的截断数量（`backend/app/repositories/mysql.py:1403`，`backend/app/repositories/mysql.py:1404`）。
    - [x] **主问 5.Q2** 对比长期画像召回与近期搜索意图召回，各自容易产生什么偏差。
3. ⭐ ALS 候选为什么在 replay 时还要经过 `as_of_ts` 过滤？
    - [x] **前置 5.P3** 看懂 ALS channel 先取候选，再过滤未来才出现的 article（`backend/app/repositories/mysql.py:1436`）。
    - [x] **主问 5.Q3** 解释模型 artifact 含有未来 item 时，单靠 request 时间切分为什么仍可能泄漏。
4. ⭐ 什么时候才启用 hot/fresh fallback？
    - [x] **前置 5.P4** 看懂只有 primary candidates 少于 page size 才补热门内容（`backend/app/repositories/mysql.py:1462`，`backend/app/repositories/mysql.py:1465`）。
    - [x] **主问 5.Q4** 解释 fallback 对可用性、个性化纯度和离线指标的 trade-off。
5. ⭐ `alpha` 到底在混合什么？
    - [x] **前置 5.P5** 看懂 `compute_alpha()` 从 behavior score 映射到 floor/ceiling 之间（`backend/app/config.py:133`）。
    - [x] **主问 5.Q5** 解释 `alpha * personalized + (1-alpha) * default` 为什么比冷/热用户硬切换更平滑（`backend/app/repositories/mysql.py:209`，`backend/app/repositories/mysql.py:348`）。
6. ⭐ `default_topic_weight_map`（alpha 混合公式里的"默认画像"）具体是怎么产出来的？
    - [x] **前置 5.P6** 看懂 `load_default_seed_topic_weights()` 只是按 `seed_key` 查 `system_profile_seed` 这一张独立表（`backend/app/repositories/profile_dao.py:70`），这张表主键是 `seed_key`（字符串），不是 `user_id`，跟 `user_profile` 是两张表、两套主键。
    - [x] **主问 5.Q6** 解释离线构建脚本（`scripts/mind_demo_pack.py:298-306`）怎么把所有 demo persona 各自的 `topic_weights` 累加、除以总量归一化、只留 top 10，产出这一份"全体平均喜好"种子；以及为什么专门另建一份 `topic_weights=[]` 的 `evaluation_empty` 种子给离线评估用（避免冷启动用户在测试里蹭到全局热门话题的光，把指标虚高）。

> 带读笔记（已讨论）
>
> - 当前理解：针对“热门内容一直推、用户真正想要的内容上不来”，第一步不是直接调权重，而是检查目标内容是否进入候选池，并区分 recall failure 与 ranking failure。
> - 可复用模式 / trade-off：候选未进入时应查 profile topic、recent query、ALS 等召回通道；候选已进入但排名低时，再检查 hotness、个性化 topic、query boost 和模型分数。热门 fallback 保可用性，但需防止 popularity feedback loop。
> - 关于候选容器的当前理解：`dict[article_id, candidate]` 让同一文章只有一个候选槽位，多条召回通道不会重复占据排序名额。
> - 可复用模式：多源聚合时先用稳定业务 ID 去重，再在 value 中累积来源、分数和 provenance。
> - trade-off：集中合并简化后续排序，但必须明确不同来源分数如何合并，否则某条通道可能被无意覆盖。
> - 关于合并规则的当前理解：`setdefault` 保证一篇文章只建一次档，`sources` 做并集，`raw_base_score` 取最大值，任一主召回命中都会将 `is_fallback` 置为 `False`。
> - 可复用模式：聚合字段可采用单调合并规则，例如来源只增不减、质量分取最大、主来源优先于兜底身份。
> - trade-off：取最大值简单稳定，但前提是各通道 raw score 可比较；否则需要归一化或分通道特征。
> - 关于 topic 截断的当前理解：画像 mapping 取当前迭代顺序前 10 个 key，搜索 mapping 取前 20 个；切片本身不按 value 排序。
> - 可复用模式：Top-N 截断前必须明确排序责任属于上游还是当前函数，避免把插入顺序误当权重顺序。
> - trade-off：截断能控制数据库查询和候选规模，但可能丢失长尾兴趣；搜索侧更大的上限给短期意图更多覆盖。
> - 关于两类兴趣信号的当前理解：长期画像稳定但可能陈旧、强化兴趣茧房；近期搜索灵敏但可能过度响应一次性、歧义或代查需求。
> - 可复用模式：推荐系统常组合 slow signal 与 fast signal，并分别设置更新速度、衰减和确认机制。
> - trade-off：增加近期信号能快速适应意图，却会提高噪声敏感度；依赖长期画像更稳定，却可能错过兴趣迁移。
> - 关于 replay 过滤的当前理解：ALS 索引可能包含回放时刻之后才出现的文章，`allowed_als_answer_ids` 会把这些未来候选排除。
> - 可复用模式：历史评估不只要切请求，还要让候选目录、统计量和模型可见状态全部服从同一 event-time 边界。
> - trade-off：在线过滤保护时间正确性，但增加一次目录校验，也可能降低可用 ALS 候选数。
> - 关于 artifact 泄漏的当前理解：request split 只隔离样本；若模型、向量索引或 ID map 使用了 cutoff 后目录，测试候选仍会携带未来信息。
> - 可复用模式：时间安全评估应同时版本化数据、特征、模型和候选目录；无法重建历史 artifact 时，至少在读取边界做 event-time 过滤。
> - trade-off：严格历史 artifact 最可信但构建昂贵；运行时过滤成本更低，却不能消除 artifact 内其他未来统计带来的全部风险。
> - 关于 fallback 条件的当前理解：仅当非兜底候选数小于 `page_size` 时，系统才加载 hot/fresh 内容补齐页面。
> - 可复用模式：把 fallback 设计为缺口填充，而不是常驻混入，可以明确区分个性化供给与可用性兜底。
> - trade-off：按需兜底减少热门内容挤占，但主召回刚好够数时可能保留质量较弱的个性化候选。
> - 关于 fallback 评估的当前理解：它能保证页面供给，却会降低个性化来源占比，并可能让最终列表指标掩盖主召回的覆盖缺口。
> - 可复用模式：分别报告 primary coverage、fallback rate、分来源 recall 和最终列表指标，避免只看聚合结果。
> - trade-off：禁用 fallback 能更纯粹地测主通道，但会制造空页；启用 fallback 改善 UX，却增加 popularity bias 风险。
> - 关于 `alpha` 的当前理解：零行为时从 floor `0.1` 起步，行为证据增加后平滑上升，并渐近接近 ceiling `0.95`。
> - 可复用模式：用饱和函数把“证据量”映射成置信权重，可避免线性权重无限增长和阈值突变。
> - trade-off：floor 让冷用户仍有少量个性化空间，ceiling 让热用户仍保留默认先验；两者都需要实验校准。
> - 关于连续混合的当前理解：行为证据小幅变化只会平滑改变个性化权重，不会在阈值两侧触发完全不同的排序。
> - 可复用模式：把默认先验与个体证据按置信度连续融合，适用于冷启动、风险评分和渐进式个性化。
> - trade-off：平滑混合提升稳定性，却可能稀释成熟用户的强信号；硬切换更纯粹但容易产生边界抖动。
> - 关于默认画像种子构建的当前理解：`system_profile_seed` 是与 `user_profile` 完全独立的一张表，主键是 `seed_key`（字符串，如 `"cold_start_default"`），不是 `user_id`——它不是一个"假用户"。内容由离线脚本把所有 demo persona 各自的 `topic_weights` 逐话题累加求和，除以总权重归一化成占比，只保留权重最高的前 10 个话题，相当于"全体用户的热门话题分布"，一次性写入这一行，不是实时计算。
> - 可复用模式：冷启动默认信号可以用"离线预计算 + 运行时查表"的方式提供，避免每次请求现场聚合全量用户数据；缺失时应 fail loudly（`RuntimeError`）而不是静默退化成空画像。
> - trade-off：另外准备一份 `topic_weights=[]` 的 `evaluation_empty` 种子专供离线评估——避免冷启动用户在测试集里"蹭"全局热门话题光环，把 Recall 指标虚高；生产与评估的冷启动口径故意分开。
> - 还没展开的问题：进入 6.P1，理解 LightGBM 线上特征名称与顺序为什么必须固定。

## 6. Day 2：LightGBM 排序与训练/服务特征一致性

1. ⭐ 线上特征为什么必须固定名称和顺序？
    - [x] **前置 6.P1** 看懂 `RANKER_FEATURE_COLUMNS` 是共享列契约（`backend/app/repositories/ranker.py:27`）。
    - [x] **主问 6.Q1** 解释同一组数值只要列顺序错了，模型为何仍能运行却给出错误结果。
2. ⭐ metadata 不兼容时为什么拒绝加载模型？
    - [x] **前置 6.P2** 看懂 `FEATURE_SCHEMA_VERSION` 和完整 feature list 两道检查（`backend/app/repositories/ranker.py:26`，`backend/app/repositories/ranker.py:62`）。
    - [x] **主问 6.Q2** 说明 fail closed 与“缺列补 0 后继续跑”各自的风险。
3. ⭐ `build_feature_dict()` 如何保持 online/offline parity？
    - [x] **前置 6.P3** 找出 hotness、topic mix、query boost、behavior 和 article age 特征（`backend/app/repositories/ranker.py:103`）。
    - [x] **主问 6.Q3** 对照 `test_runtime_base_score_matches_mind_training_formula()`，解释为什么需要针对公式做契约测试（`tests/test_train_eval_mind.py:136`）。
4. ⭐ `score_candidates()` 返回 `None` 和返回 `[]` 有什么区别？
    - [x] **前置 6.P4** 看懂 `None` 表示兼容模型不可用，空列表表示输入没有 candidate（`backend/app/repositories/ranker.py:79`）。
    - [x] **主问 6.Q4** 解释 default arm 为什么可以手工公式降级，而显式 LGB experiment arm 为什么应报错（`backend/app/repositories/mysql.py:324`）。
5. ⭐ 为什么先组装所有 `feature_dicts` 再批量预测？
    - [x] **前置 6.P5** 看懂候选先进入 `feature_dicts`，之后统一调用 model（`backend/app/repositories/mysql.py:281`，`backend/app/repositories/mysql.py:324`）。
    - [x] **主问 6.Q5** 对比 batch inference 与逐 candidate 调用在延迟、特征顺序和错误处理上的差别。
6. ⭐ `lgb_ranker_v1.txt` 和 `lgb_ranker_v1_meta.json` 分别是什么，别搞混？
    - [x] **前置 6.P6** 看懂 `.txt` 是 LightGBM 原生序列化格式，真实存了上百棵树的 `split_feature`/`num_leaves`/叶子值（`build/mind_models/lgb_ranker_v1.txt:1-15`），是模型本体，不是"特征"。
    - [x] **主问 6.Q6** 解释 `.json` 只是这个项目自己写的配套清单——`features` 字段是"名字 → 第几列"的顺序表，不是取值编码，也不含每个特征的业务含义说明；`.txt` 内部其实自带一行 `feature_names=...`，是第二份顺序真相来源，但当前 `load_model()` 没有拿它跟 `meta.json`/`RANKER_FEATURE_COLUMNS` 做交叉校验。

> 带读笔记（已讨论）
>
> - 关于特征列契约的当前理解：LightGBM 按数值位置解释输入；字段数量不变但顺序错位时，模型仍能运行并产生静默错误。
> - 可复用模式：训练与服务共享单一 feature-name/order 常量，并把完整顺序写入模型 metadata 做加载校验。
> - trade-off：固定契约降低了随意增删特征的灵活性，但换来可检测的版本演进和线上语义安全。
> - 关于静默错位的当前理解：树节点使用列索引做阈值判断；同长度浮点矩阵能通过结构检查，但列索引对应的业务含义可能已经改变。
> - 可复用模式：除类型与 shape 外，还应校验 feature schema version、完整有序列名，必要时保存训练数据契约 hash。
> - trade-off：严格语义检查会拒绝部分“看似可运行”的旧模型，但比持续输出不可察觉的错误分数更安全。
> - 关于模型 metadata 校验的当前理解：schema version 是粗粒度版本门，完整有序 feature list 是精确语义门；任何一项不匹配都拒绝加载。
> - 可复用模式：版本号用于表达有意变更，完整契约用于捕获漏升版本、顺序漂移和名称错拼。
> - trade-off：双重校验更严格，会降低旧 artifact 的兼容性，但能把错误暴露在加载阶段而不是用户请求阶段。
> - 关于 Python 后端选型的面试回答：这个项目同时包含离线训练和在线推理。训练脚本直接复用后端的特征契约（`scripts/train_eval_mind.py:25-28`），FastAPI 启动时直接加载 Python LightGBM 模型（`backend/app/main.py:44-47`），因此选择 Python 能降低特征漂移、重复实现和独立模型服务的部署成本。Java 当然能做；如果未来进入大团队、高吞吐、成熟 JVM 基建环境，我会考虑 Java 承担 API/业务编排，Python 模型服务独立部署。当前项目只是原型，不能用本地延迟数据证明 Python 已满足生产规模。
> - 关于 fail closed 的当前理解：metadata 不兼容时拒绝使用该 LightGBM 模型，能在加载阶段暴露部署错误；请求报错还是走降级由调用方决定。
> - 可复用模式：把“artifact 不存在”和“artifact 存在但契约无效”分开处理，只在明确允许的路径使用降级策略。
> - trade-off：fail closed 可能降低模型或实验 arm 的可用性；补 0 虽能继续推理，却会把“未知”伪装成真实数值，使树走入错误分支并掩盖故障。
> - 关于线上特征分组的当前理解：`base_score` / `article_hot_score` 表示热度，`topic_match_score` 表示长期个性化与默认画像的混合，`query_recall_boost` 表示近期搜索意图，`user_behavior_score` 表示行为证据，`article_age_hours` 表示文章年龄。
> - 可复用模式：先按业务语义构造具名 feature dict，再按照共享列契约转换成模型矩阵，便于检查线上特征含义。
> - trade-off：同时保留原始信号和组合信号能增加模型表达力，但会提高共线性、契约维护和训练服务一致性的成本。
> - 关于公式契约测试的当前理解：只检查字段、类型和 shape 无法发现同名特征的公式漂移；固定输入输出断言能锁定训练与服务的数值语义。
> - 可复用模式：为关键特征准备最小 golden case，让离线公式和线上 builder 在具体数值上保持一致。
> - trade-off：精确公式测试能阻止静默漂移，但有意调整公式时必须同步更新训练、服务、schema 版本与测试。
> - 关于返回值状态的当前理解：`None` 表示兼容模型不可用，`[]` 表示模型可用但本次没有候选需要评分；两者驱动不同的调用方决策。
> - 可复用模式：不要用正常数值或空集合承载故障状态；用显式 sentinel 或结果类型区分 unavailable、empty 和 success。
> - trade-off：`Optional[list]` 简单直接，但要求每个调用方正确分支；状态继续增多时应考虑显式 result 类型。
> - 关于实验降级的当前理解：`default` arm 优先保证 feed 可用，可以退回手工公式；显式 LightGBM arm 承诺实际运行该模型，缺模型时必须报错。
> - 可复用模式：按调用意图定义降级策略；普通生产路径可以有可观测 fallback，实验、审计和强一致路径应 fail loudly。
> - trade-off：默认降级提高可用性但可能降低排序质量；实验报错牺牲局部可用性，却保护实验归因和故障可见性。
> - 关于批量评分数据流的当前理解：每篇候选的模型特征和文章上下文按相同顺序分别追加；模型返回的第 `i` 个分数再通过索引配回第 `i` 篇文章。
> - 可复用模式：批处理前显式维护输入与业务对象的一一对应关系，并用测试保护长度和顺序不变量。
> - trade-off：平行列表实现简单高效，但中途漏 append 就会错配；更复杂时可用带 ID 的结构减少隐式顺序依赖。
> - 关于 batch inference 的当前理解：多篇候选先组成多行矩阵，再通过一次 `model.predict(rows)` 返回同顺序的多个分数。
> - 可复用模式：集中使用共享列顺序构造矩阵、保留输入与业务对象的索引映射，并校验预测数量与候选数量一致。
> - trade-off：batch 减少固定调用开销并统一特征排列，但单个非法输入可能影响整批；逐篇调用更易隔离错误，却增加延迟并引入部分成功处理。
> - 关于 model artifact 组成的当前理解：`lgb_ranker_v1.txt` 是 LightGBM Booster 的原生序列化文件，按 `Tree=N` 存储每棵树的 `split_feature`/阈值/叶子值，是模型本体（428KB，上百棵树）；`lgb_ranker_v1_meta.json` 是这个项目自建的元数据契约，核心是 `features` 顺序清单 + `feature_schema_version`，附带 dataset、数据指纹、`training_cutoff_ts`、样本数和 `roc_auc`/`pr_auc`/`log_loss` 等离线指标。
> - 可复用模式：模型文件负责"怎么算"（树结构和参数），metadata 文件负责"输入该长什么样"（顺序契约 + 版本 + 可复现性指纹），两者职责分离；metadata 是工程约定，不是 LightGBM 强制要求。
> - trade-off：`.txt` 内部其实自带一行 `feature_names=...`，是第二份顺序真相来源；但当前 `load_model()` 只交叉校验 `meta.json` 与 `RANKER_FEATURE_COLUMNS`，没有再对比模型自带的 `feature_names`，两者未来若不同步会是个隐藏风险点，属于可以主动指出的改进项。
> - **【复习 Round 2 沟通薄弱点】**：第一次表达时把 `.txt` 文件错说成"它的特征"，混淆了"模型本体"和"喂给模型的特征"两个概念。正确说法：`.txt` 是训练好的模型本体（几百棵树的分裂规则），`.json` 才是特征名字的顺序清单（只管顺序，不含每个特征的业务含义说明）。可直接背的话术："txt 文件是训练好的 LightGBM 模型本身……json 文件不是模型，是一份配套清单，记了训练时用的是哪 16 个特征、按什么顺序排——线上打分必须照这个顺序拼数字喂给模型，顺序错了模型不会报错，但会用错位的数字瞎算，分数全错。"
> - 还没展开的问题：进入 7.P1，理解 `resolve_query_key()` 对数字查询的快速解析路径。

### 新 Session 实验计划：Pointwise Classifier vs LambdaRank

> 状态：已于 2026-07-24 完成实现、离线实验和配对 bootstrap；线上 artifact
> 与主报告保持不变。

**实验目标**

在完全相同的时间切分、请求样本和特征契约下，对比当前
`LGBMClassifier(objective="binary")` 与
`LGBMRanker(objective="lambdarank")` 的离线排序效果。实验完成标准是得到
公平、可复现的对比证据，不是预设 LambdaRank 必须获胜。

**固定不变的实验条件**

1. 继续使用 `_request_split()` 的全局时间 request holdout，禁止随机切 item。
2. 两个模型共享同一份 `train_features`、`test_features` 和
   `RANKER_FEATURE_COLUMNS`。
3. 第一轮只改变训练 objective；树数量、学习率、叶子数等共享参数保持一致，
   不同时调参或顺手修其他超参数，避免混淆变量。
4. 测试集只用于最终比较。若后续需要调参，应从训练分区再拆 validation，
   不能反复观察 test 后修改参数。
5. 主要比较 NDCG@10；同时报告 Recall@5/10、NDCG@5、MRR 和
   Category Diversity@10。LambdaRank 的输出是排序分数，不把它当成校准后的
   点击概率比较 LogLoss。
6. 本实验先保持纯离线，不替换当前线上 `lgb_ranker_v1.txt`，也不改变
   `backend/app/repositories/ranker.py` 的加载行为。

**实施步骤**

1. **锁定现有基线**
   - 保留 `scripts/train_eval_mind.py:507-520` 的 classifier 训练和预测逻辑。
   - 保留现有 `ranking_arms["lightgbm"]`、结论生成逻辑和线上模型 artifact，
     避免破坏已有报告消费者。
   - 记录当前 fingerprint、采样 request 数和 LightGBM 排序指标，作为回归基线。

2. **增加 request group helper**
   - 在 `scripts/train_eval_mind.py` 增加小型 helper，例如
     `_request_group_sizes(frame) -> list[int]`。
   - 按当前行顺序生成每个完整 `request_id` 的候选数量；校验 group 总和等于
     frame 行数，并拒绝同一 request 出现在多个不连续区块。
   - 在 `tests/test_train_eval_mind.py` 增加：正常 group 大小、非连续 request
     拒绝、总行数守恒三个测试。

3. **增加显式实验开关**
   - 给 `scripts/train_eval_mind.py` 增加
     `--compare-lgb-objectives`，默认关闭，保证原命令行为和运行成本不变。
   - 开启时创建 `LGBMRanker(objective="lambdarank", metric="ndcg", ...)`。
   - `fit()` 使用相同训练特征和 label，并传入训练 request group；
     `predict()` 对同一 `test_features` 产生 ranking score。
   - 不使用 test group 做 early stopping 或参数选择。

4. **生成独立对比报告**
   - 增加 `--comparison-output`，建议默认写入
     `docs/metrics/mind_lgb_objective_comparison.json`。
   - 报告至少包含：dataset fingerprint、split/cutoff、共享 feature schema、
     两套模型配置、训练耗时、两套排序指标和
     `lambdarank - pointwise` 的逐指标 delta。
   - 不覆盖 `docs/metrics/mind_recommendation.json`；确认结果可信后，再单独决定
     是否更新主报告和 README。

5. **验证与运行**
   - 先运行：
     `python -m pytest -q tests/test_train_eval_mind.py`
   - 再运行：
     `python -m ruff check scripts/train_eval_mind.py tests/test_train_eval_mind.py`
   - 确认 `build/mind_normalized` 数据存在后，运行带
     `--compare-lgb-objectives` 的完整实验。
   - 验证 pointwise 基线没有漂移、两个模型使用相同 request 数、group 行数守恒、
     对比 JSON 可重复生成，且当前线上模型 artifact 未被实验覆盖。

6. **解释结果，而不是只挑赢家**
   - 若 LambdaRank 提升 NDCG，但 Recall 或多样性下降，明确写出指标 trade-off。
   - 若两者接近，增加按 request 配对的 bootstrap 置信区间，再判断差异是否稳定。
   - 若 LambdaRank 没提升，保留负结果：当前特征、样本规模或参数下，
     pointwise baseline 已足够有竞争力；不能外推为 LambdaRank 普遍无效。
   - 只有离线证据稳定后，才另开任务讨论 artifact 命名、线上 score 语义和部署切换。

**已知陷阱**

- Ranker 的 `group` 必须对应连续、完整的 request 候选块；只做普通
  `groupby().size()` 而不验证行连续性，可能掩盖错序数据。
- 不能给两个模型使用不同负样本、不同采样 request 或不同特征列。
- 不能用测试集调参后仍把它称为 untouched test。
- 不能把 LambdaRank raw score 描述成 CTR probability。
- 第一轮不要同时改 `subsample`、特征公式或线上 artifact，否则无法判断增益来自
  objective 还是其他变化。

**执行结果（2026-07-24）**

- 独立报告：`docs/metrics/mind_lgb_objective_comparison.json`。
- 数据与样本：normalized fingerprint 为
  `643c53b0ce5fddf5e08a8d6f8e491ddec607a3f56c335c44d872e6e74cbd4b52`；
  训练 20,000 个 request / 753,687 行，测试 10,000 个 request / 421,431 行；
  group 行数均与样本行数守恒。
- Pointwise：NDCG@10 `0.362955`、Recall@10 `0.596866`、Recall@5
  `0.421278`、Category Diversity@10 `4.4234`。
- LambdaRank：NDCG@10 `0.363497`、Recall@10 `0.594341`、Recall@5
  `0.427401`、Category Diversity@10 `4.0748`。
- `LambdaRank - Pointwise`：NDCG@10 `+0.000542`、NDCG@5 `+0.003525`、
  MRR `+0.001629`、Recall@5 `+0.006123`、Recall@10 `-0.002525`、
  Category Diversity@10 `-0.3486`。
- 2,000 次 request 配对 bootstrap 的 95% 区间：NDCG@10
  `[-0.002928, 0.003905]`，不能建立稳定赢家；Recall@5
  `[0.000734, 0.011730]` 为稳定提升，但 Category Diversity@10
  `[-0.367000, -0.331298]` 为稳定下降，其余指标区间跨 0。
- 结论仅适用于当前特征、样本和共享超参数：LambdaRank 没有建立稳定的主指标优势，
  且存在明确多样性代价，因此不替换当前线上模型；不能外推为 LambdaRank 普遍无效。

**原新 session 启动语句（已执行）**

> 读取 `zhihurec_interview_questions.md` 中“新 Session 实验计划：
> Pointwise Classifier vs LambdaRank”，按计划先做基线与 group helper，
> 暂不改线上 artifact。

## 7. Day 2：搜索意图如何进入下一次推荐

1. ⭐ 用户输入的英文文字如何变成内部 `query_key`？
    - [x] **前置 7.P1** 看懂 `resolve_query_key()` 的 numeric fast path（`backend/app/repositories/query_resolver.py:128`）。
    - [x] **主问 7.Q1** 追踪 display query → topic name → headline/abstract lexical match，并解释无法解析时为何返回 422 而不是编造 topic。
2. ⭐ 一次 `/search` 会写入哪些状态？
    - [x] **前置 7.P2** 找到 `claim_event_id()`、`record_search_query()` 和 `append_recent_query()`（`backend/app/repositories/mysql.py:532`，`backend/app/repositories/mysql.py:539`，`backend/app/repositories/mysql.py:546`）。
    - [x] **主问 7.Q2** 区分事件日志、recent query 列表和 behavior score，各自服务什么后续逻辑。
3. ⭐ 最近搜索怎样变成 feed 的 topic scores？
    - [x] **前置 7.P3** 看懂 `load_recent_query_topic_scores()` 把 query map 行乘以时间 multiplier（`backend/app/repositories/profile_dao.py:94`，`backend/app/repositories/profile_dao.py:132`）。
    - [x] **主问 7.Q3** 对比 legacy、decay、gated 三种 signal 语义（`backend/app/repositories/search_signal.py:59`）。
4. ⭐ 为什么搜索结果点击是“更强确认”？
    - [x] **前置 7.P4** 看懂 query topics 与 article topics 的交集 `overlap_topic_ids`（`backend/app/repositories/mysql.py:790`，`backend/app/repositories/mysql.py:792`）。
    - [x] **主问 7.Q4** 解释 overlap topic 使用更大 delta，并给 recent query 写 `confirmed_ts` 的业务含义（`backend/app/repositories/mysql.py:797`，`backend/app/repositories/mysql.py:815`）。
5. ⭐ 搜索机制实验能说到什么程度？
    - [x] **前置 7.P5** 记住 3 个 deterministic scenario 中只有 1 个改变 top-10 target share，mean delta 为 `0.2`（`docs/metrics.md:29`）。
    - [x] **主问 7.Q5** 用一句话区分“机制接通”与“真实用户搜索提升推荐效果”。

> 带读笔记（已讨论）
>
> - 关于 numeric fast path 的当前理解：合法数字 `query_key` 已经是数据库认识的内部标识，只需统一空格格式，无需再执行文本匹配。
> - 可复用模式：优先识别并规范化强标识符；只有缺少强标识符时，才进入成本更高、结果更模糊的解析链。
> - trade-off：fast path 减少查询和误匹配，但调用方必须明确区分内部 key 与用户展示文本。
> - 关于文本解析链的当前理解：`resolve_search_query()` 按 display query → topic display name → article headline/abstract 逐级放宽证据，并最终映射到已有 `query_key`。
> - 可复用模式：对模糊输入采用“强证据优先、弱证据兜底”的确定性解析；所有证据都不足时显式失败，而不是伪造业务含义。
> - trade-off：返回 422 会牺牲“任意输入都有结果”的表面可用性，但能避免错误 topic 污染搜索结果、recent query 和后续用户画像。
> - 关于搜索写入顺序的当前理解：事务先调用 `claim_event_id()`；只有事件首次被 claim，才锁定 profile、调用 `record_search_query()`，再调用 `append_recent_query()`。
> - 可复用模式：先做幂等 claim，再执行有副作用的日志与状态更新，避免请求重试重复生效。
> - trade-off：claim 与后续写入必须处于同一事务；否则可能出现“已经 claim，但业务状态没更新”的半完成状态。
> - 关于三类搜索状态的当前理解：`user_event` 是可审计、可重放的事实流水；`recent_queries_json` 是供近期意图计算使用的有界派生状态；`behavior_score` 是控制个性化混合强度的聚合值。
> - 可复用模式：把不可变事实、面向具体功能的短期状态、压缩后的控制信号分开存储，避免一份数据承担互相冲突的职责。
> - trade-off：派生状态读取快，但必须由同一事务或可靠事件消费保持与事实流水一致；事实流水更完整，直接在线聚合则成本更高。
> - 关于 query topic score 的当前理解：每条映射的原始相关度乘以该次搜索当前的时间 multiplier，得到有效分数；同一 topic 被多次搜索命中时保留最大值。
> - 可复用模式：把静态相关度与动态时效权重拆开计算，使映射表无需随时间持续改写。
> - trade-off：取最大值能防止重复搜索无限累加，但会丢掉“多次独立搜索共同增强意图”的频次信息。
> - 关于三种搜索信号的当前理解：legacy 权重恒为 1；decay 从 `query_ts` 按半衰期减弱；gated 要求确认后才能打开搜索召回，并把确认信号切换为更强、更长寿的 multiplier。
> - 可复用模式：用 experiment arm 配置同一份用户状态的解释方式，而不是为每个实验复制整套 feed 流程。
> - trade-off：legacy 简单但旧意图不会消失；decay 更符合时效性但参数敏感；gated 减少误触发召回，却可能漏掉没有点击反馈的真实意图。
> - 关于 overlap topic 的当前理解：`overlap_topic_ids` 是 query topics 与被点击 article topics 的集合交集，表示搜索意图和实际点击内容共同支持的主题。
> - 可复用模式：用集合交集提取两类行为证据的一致部分，再对一致证据施加不同权重。
> - trade-off：交集信号精度更高，但 topic 标注缺失或过粗时会漏掉语义上相关、ID 上不相交的确认行为。
> - 关于搜索点击确认的当前理解：用户输入 query 是声明意图，点击相关 article 是行为确认；两者重合的 topic 使用更大 delta，`confirmed_ts` 则把 recent query 标记为可用于 gated recall 的确认信号。
> - 可复用模式：把“表达意图”和“兑现行为”作为两级证据，只有一致时才提升信号置信度与生命周期。
> - trade-off：点击确认能降低误触发，但点击也可能受标题党、位置偏差影响，不能等同于长期真实偏好。
> - 关于 intent scenario 指标的当前理解：3 个固定 demo 场景中只有 1 个改变了 top-10 目标类别占比，mean delta 为 `0.2`。
> - 可复用模式：先用 deterministic scenario 验证信号链是否能影响预期输出，再用真实日志或在线实验验证用户价值。
> - trade-off：固定场景易复现、易定位机制问题，但样本极小且缺少真实用户选择，不能估计泛化效果。
> - 关于证据边界的当前理解：当前结果只证明 search → profile signal → feed 的链路能改变部分固定 demo 输出；MIND 没有搜索日志，因此不能声称 CTR、因果提升或真实用户收益。
> - 可复用模式：汇报实验时把“功能接通”“离线相关性”“在线因果收益”分成不同证据等级，结论不得越级。
> - trade-off：谨慎表述看起来不够亮眼，但能避免把小型机制测试包装成生产效果，提升技术可信度。
> - 还没展开的问题：进入 8.P1，理解事件 fingerprint 为什么排除时间字段。

## 8. Day 3：事务、幂等、Outbox 与 Kafka

1. ⭐ `idempotency_fingerprint` 为什么故意忽略 retry timestamp？
    - [x] **前置 8.P1** 看懂 fingerprint 包含业务身份字段，但不包含 `event_ts` / `producer_ts`（`backend/app/events/schema.py:84`）。
    - [x] **主问 8.Q1** 解释“同一 payload 重试”与“复用 event ID 发送不同 article”为什么必须得到不同处理（`tests/test_event_stream.py:45`）。
2. ⭐ `claim_event_id()` 如何区分首次、重复和冲突？
    - [x] **前置 8.P2** 看懂唯一键插入失败后会回读原 fingerprint（`backend/app/repositories/event_dao.py:17`）。
    - [x] **主问 8.Q2** 解释普通重复为什么返回成功，payload 冲突为什么应返回 409。
3. ⭐ `FOR UPDATE` 防住的是什么并发 bug？
    - [x] **前置 8.P3** 看懂 `fetch_profile_row(..., for_update=True)` 给 user profile 行加锁（`backend/app/repositories/profile_dao.py:23`）。
    - [x] **主问 8.Q3** 用两个并发 click 推演没有行锁时的 lost update（`tests/test_mysql_smoke.py:133`）。
4. ⭐ Transactional Outbox 解决了哪一个双写窗口？
    - [x] **前置 8.P4** 看懂业务事务内调用 `_enqueue_raw_event()`，最终写入 `event_outbox`（`backend/app/repositories/mysql.py:1368`，`backend/app/events/outbox.py:34`）。
    - [x] **主问 8.Q4** 对比“先 commit MySQL 再发 Kafka”与“先发 Kafka 再 commit MySQL”各自可能丢什么。
5. ⭐ 多个 outbox publisher 为什么不会同时抢到同一行？
    - [x] **前置 8.P5** 看懂 `FOR UPDATE SKIP LOCKED` 和 pending → publishing 状态变更（`backend/app/events/outbox.py:105`，`backend/app/events/outbox.py:123`）。
    - [x] **主问 8.Q5** 解释 stale claim 恢复、指数退避和 dead 状态分别处理哪类失败（`backend/app/events/outbox.py:84`，`backend/app/events/outbox.py:190`）。
6. ⭐ 为什么 Kafka consumer 仍必须幂等？
    - [x] **前置 8.P6** 看懂 `ProfileEventApplier.apply_event()` 先 claim，再按 event type 更新，最后写 training outbox（`backend/app/events/consumer.py:68`，`backend/app/events/consumer.py:87`）。
    - [x] **主问 8.Q6** 解释 at-least-once、重复消费、无效消息进 DLQ、暂时性错误重试之间的关系（`backend/app/events/consumer.py:452`，`backend/app/events/consumer.py:459`，`backend/app/events/consumer.py:484`）。
7. ⭐ `claim_feed_request` 是 feed 级幂等，和事件 fingerprint 是两种不同实现，为什么？
    - [x] **前置 8.P7** 看懂 `claim_feed_request` 用 `INSERT ... ON DUPLICATE KEY UPDATE` + `cursor.rowcount == 1` 判断"全新请求"还是"重放"（`backend/app/repositories/sponsored_dao.py:65-84`）。
    - [x] **主问 8.Q7** 解释重放分支为什么还要 `SELECT ... FOR UPDATE` 回读旧参数、和本次参数比对形状（`existing_shape != requested_shape`），不一致就抛 `IdempotencyConflictError` 转 409（`sponsored_dao.py:96-126`，`main.py` 的 `idempotency_conflict_handler`）；以及 `new_feed_request` 这个布尔值下游怎么用来跳过广告重复分配（`mysql.py` 里 `if not new_feed_request: load_sponsored_deliveries_for_request(...)`）。
8. ⭐ 广告预算/频次的 read-modify-write 为什么必须在同一事务的行锁里做？
    - [x] **前置 8.P8** 看懂 `sponsored_campaign_daily_state` 主键 `(campaign_id, budget_date)`、`sponsored_user_daily_frequency` 主键 `(campaign_id, user_id, budget_date)`（`sql/schema.sql:276`，`sql/schema.sql:289`），`reserve_sponsored_delivery()` 里两个 `SELECT ... FOR UPDATE` 锁的正是这两行（`sponsored_dao.py:310`，`sponsored_dao.py:367`）。
    - [x] **主问 8.Q8** 推演没有行锁时两个并发请求同时读到"预算还够"、都通过检查、都写入 delivery、最终合计超预算的竞态；解释为什么这里锁到的是纯 record lock 而非间隔锁（等值命中唯一主键 + upsert 先保证行存在），以及它和 `claim_feed_request` 锁保护的是两类不同并发场景（同一 request_id 重放 vs 不同请求抢同一份共享预算）。
9. ⭐ 点击事件的 `event_id` 到底跟着什么走？反复点同一篇文章会不会被重复计入画像？
    - [x] **前置 8.P9** 看懂服务端兜底生成是纯随机 UUID（`new_event_id()` = `f"evt-{uuid.uuid4().hex}"`，`backend/app/events/schema.py:27`），但真实前端并不依赖这个兜底——`product-frontend/src/pages/FeedPage.tsx:109` 客户端自己拼出确定性字符串 `` `click-${user_id}:${requestId}:${articleId}` ``。
    - [x] **主问 8.Q9** 解释幂等防的是"同一次提交动作被重复发送"，不是"同一篇文章被点了几次"；由于 `event_id` 由 `(user_id, requestId, article_id)` 确定性拼出，同一次 feed 请求（同一个 `requestId`）内重复点同一篇文章会被服务端幂等去重、只算一次，只有换一次新的 `requestId`（下拉刷新/翻页）才会重新计入画像；并说明这属于"应对 at-least-once 网络投递的幂等设计"，和笼统的"防御性编程"不是同一个概念——真正的防御性编程体现在前端 `trackedRef.current`（`FeedPage.tsx:71`）防止同一次渲染重复上报。

> 带读笔记（已讨论）
>
> - 关于事件 fingerprint 的当前理解：指纹覆盖用户、事件类型、article、query、request 等业务身份字段，但排除 `event_ts` 和 `producer_ts`，所以同一 payload 的重试保持同一指纹，业务内容变化则产生不同指纹。
> - 可复用模式：幂等键标识“哪一次操作”，payload fingerprint 标识“这次操作声称做什么”，两者组合才能区分安全重试和键复用冲突。
> - trade-off：排除传输时间允许重试，但任何被排除字段都不能影响业务语义，否则不同操作可能被误判成同一次。
> - 关于重试与冲突的当前理解：相同 `event_id`、相同 fingerprint 是同一次操作的安全重试；相同 `event_id`、不同 fingerprint 表示同一幂等键被用于不同业务操作，不能静默去重。
> - 可复用模式：幂等处理不能只判断“键是否存在”，还必须验证旧请求与新请求的业务内容是否一致。
> - trade-off：保存 fingerprint 增加少量存储和比较成本，但避免错误客户端悄悄覆盖或丢失不同操作。
> - 关于 claim 回读的当前理解：唯一键冲突只证明 `event_id` 已存在；回读旧 fingerprint、user 和 event type 后，才能区分同一操作重试与错误复用事件 ID。
> - 可复用模式：数据库唯一约束负责原子地判定“首次或已存在”，应用层再比较业务摘要判定“重复或冲突”。
> - trade-off：重复路径多一次查询，但换来并发下可靠的语义校验，不能仅靠客户端保证 ID 不复用。
> - 关于重复响应语义的当前理解：相同 payload 的重复请求虽然不再执行副作用，但目标状态已达成，因此返回成功；不同 payload 复用同一事件 ID 是调用契约冲突，返回 409 要求调用方修正。
> - 可复用模式：幂等 API 的成功表示“期望操作已经生效”，不等于“本次请求新执行了一次”；不可自动恢复的请求冲突应显式暴露。
> - trade-off：重复也返回成功会隐藏“首次还是重试”的差别，若业务需要观测可另加 debug/metric，但不能因此重复执行副作用。
> - 关于 profile 行锁的当前理解：`SELECT ... FOR UPDATE` 让同一用户画像的读改写事务串行执行；后来的事务等待前一个提交，再读取最新画像。
> - 可复用模式：对单行聚合状态执行 read-modify-write 时，在读取阶段就锁定该行，避免多个事务基于同一旧快照计算。
> - trade-off：行锁保证正确性但会让同一热点用户的更新排队；锁范围应保持到必要最小，事务内避免慢操作。
> - 关于 lost update 的当前理解：若两个 click 都读取 `10` 并各自写回 `13`，最终一次增量被覆盖；行锁让第二个请求在第一个提交后读取 `13`，再写成 `16`。
> - 可复用模式：并发 bug 要用明确时间线推演“读了什么、算了什么、最后谁覆盖谁”，而不能只看单个 UPDATE 是否正确。
> - trade-off：也可用数据库原子增量避免简单计数丢失，但这里还同时更新 JSON 画像，仍需要协调完整 read-modify-write。
> - 关于 outbox enqueue 的当前理解：业务事务不直接发送 Kafka，而是通过同一 MySQL connection 把事件写入 `event_outbox`；事务提交后由独立 publisher 异步发送。
> - 可复用模式：把“需要发送消息”先表示成数据库内的持久化事实，与业务状态一起原子提交。
> - trade-off：消除了业务事务与消息持久化之间的双写不一致，但引入 publisher、重试、积压监控和最终一致延迟。
> - 关于双写窗口的当前理解：先提交 MySQL 再发 Kafka，崩溃会留下业务状态但丢消息；先发 Kafka 再提交 MySQL，崩溃或回滚会让下游看到从未生效的业务事件。
> - 可复用模式：无法跨系统原子提交时，把跨系统动作转换为本地事务内的 durable intent，再异步完成外部副作用。
> - trade-off：Outbox 保证最终可重试，不保证 Kafka 只收到一次，因此下游仍需幂等。
> - 关于 outbox claim 的当前理解：publisher 用 `FOR UPDATE SKIP LOCKED` 锁定自己领取的 pending 行，并在同一事务中改为 publishing；其他 publisher 跳过这些锁，领取别的行。
> - 可复用模式：短事务只负责“领取任务并标记所有权”，耗时的外部发送放到事务外执行，提高并发吞吐。
> - trade-off：SKIP LOCKED 避免 worker 相互等待，但 publishing worker 崩溃后需要 stale claim 恢复，否则任务会永久卡住。
> - 关于 outbox 失败状态的当前理解：stale recovery 把崩溃 worker 遗留的 publishing 行重新置为 pending；指数退避为暂时故障降低重试频率；达到上限后标记 dead，停止无限重试并等待人工处理。
> - 可复用模式：按“执行者丢失、依赖暂时失败、消息持续失败”分类恢复策略，而不是所有失败统一立即重试。
> - trade-off：dead letter 防止毒消息拖垮系统，但需要监控、告警和人工或自动修复流程，否则只是把问题藏起来。
> - 关于 consumer 事务顺序的当前理解：consumer 开启 MySQL 事务后先 claim event ID，首次事件才按类型更新画像；随后幂等写入 training outbox，最后统一 commit。
> - 可复用模式：消费端把去重、业务状态更新和下游消息意图放入同一本地事务，避免 offset 推进前出现部分成功。
> - trade-off：事务提高一致性，但消费处理越慢，锁持有和 Kafka lag 越高；耗时外部调用不应放进事务。
> - 关于消费失败分类的当前理解：at-least-once 允许 offset 未提交时重复投递，数据库 claim 让重复消息不重复更新；无法解析或校验失败的消息进入 DLQ 后提交 offset；暂时性依赖错误不提交，按上限重试。
> - 可复用模式：按“已成功但确认丢失、永久无效、暂时失败”分类消息，分别使用幂等、DLQ 和 retry。
> - trade-off：提交 DLQ offset 能避免毒消息阻塞分区，但 DLQ 发布本身必须可靠；重试期间该分区后续消息也会等待。
> - 关于 `claim_feed_request` 幂等的当前理解：靠 `INSERT ... ON DUPLICATE KEY UPDATE`（更新字段设成它自身）配合 `cursor.rowcount == 1` 区分"全新插入"与"命中已有行的空更新"；命中已有行时再 `SELECT ... FOR UPDATE` 回读旧参数，与本次参数逐字段比对，不一致才判定为幂等键复用冲突，抛 `IdempotencyConflictError` → 409。
> - 可复用模式：这是和 §8.P1-P2 事件 fingerprint 不同的第二种幂等实现——用数据库唯一键的 upsert 语义原子地区分首次/重放，而不是先查后插；`FOR UPDATE` 顺带把同一 request_id 并发重放也串行化了。
> - trade-off：`new_feed_request` 这个布尔值继续下传，决定广告分配要不要重新跑；多一次回读比较，换来"同 ID 不同参数"不会被静默吞掉。
> - 关于广告预算/频次行锁的当前理解：`sponsored_campaign_daily_state`（主键 `campaign_id+budget_date`）和 `sponsored_user_daily_frequency`（主键 `campaign_id+user_id+budget_date`）各是一行共享计数器；`reserve_sponsored_delivery` 先 upsert 保证行存在，再 `SELECT...FOR UPDATE` 锁住这一行，在同一事务里读余量、判断、`INSERT delivery`、`UPDATE` 累加，锁到事务提交才释放。
> - 可复用模式：等值命中一个已保证存在的唯一键，InnoDB 只加纯 record lock，不升级为 gap lock/next-key lock；把"确保行存在"的 upsert 放在锁之前，是刻意把锁的范围收窄到最小，不同 campaign/不同用户之间互不阻塞。
> - trade-off：这把锁和 `claim_feed_request` 的锁保护的是两类并发——一个防"同一 request_id 被重放"，一个防"不同请求抢同一份共享预算/频次"；热点 campaign 会有请求排队，但正确性优先于极端并发吞吐。
> - 关于点击 `event_id` 的当前理解：服务端兜底生成（`new_event_id()`）是纯随机 UUID，跟内容无关；但真实前端 `product-frontend/src/pages/FeedPage.tsx:109` 并不依赖这个兜底，而是自己拼一个确定性字符串 `click-{user_id}:{requestId}:{articleId}`。
> - 可复用模式：幂等 key 可以是纯随机 token（只负责"认出同一次提交"），也可以是从业务字段确定性拼出来的字符串（额外获得"同一范围内自动去重"的效果）；本项目前端选择了后者，把"同一页 feed 内重复点同一篇文章"也顺带去重了。
> - trade-off：这个设计意味着"同一 `requestId`（同一页 feed）内重复点同一篇文章只算一次"，只有拿到新的 `requestId`（下拉刷新/翻页）才会重新计入画像——这是产品行为，不是 bug；但也意味着无法单纯从 event_id 本身判断"这是不是同一次真实点击"，必须结合 `requestId` 的语义一起理解。
> - **【复习 Round 2 薄弱点】**：口头断言"用户真实分开点击同一篇文章 N 次，每次都独立计入画像"时，没有先查前端代码就下结论，属于臆断。正确认知：是否被去重取决于是否共享同一个 `requestId`，不能脱离前端实现空谈后端幂等的效果。教训：涉及"客户端具体怎么做"的判断，必须先查前端代码，不能只靠后端的通用容错设计去反推。
> - 关于"幂等设计"与"防御性编程"的当前理解：服务端 claim+fingerprint 校验更准确的定位是"应对 at-least-once 网络投递的幂等设计"，这是分布式系统可靠性范畴；前端 `trackedRef.current`（`FeedPage.tsx:71`）防止同一次渲染/effect 重复触发上报，这部分才是经典意义上的防御性编程。两者不是同一个概念，面试时应分开讲更准确。
> - 还没展开的问题：进入 9.P1，观察前端 impression 去重 identity。

## 9. Day 3：产品闭环、质量门槛与高压追问

1. ⭐ 前端为什么用 `(user_id, request_id, article_id)` 去重 impression？
    - [x] **前置 9.P1** 看懂 `trackedRef` 保存已经提交的 item identity（`product-frontend/src/pages/FeedPage.tsx:18`，`product-frontend/src/pages/FeedPage.tsx:70`）。
    - [x] **主问 9.Q1** 解释失败后删除 key 允许重试，以及为什么不能只按 article ID 去重（`product-frontend/src/pages/FeedPage.tsx:92`）。
2. ⭐ persona 快速切换时如何避免显示旧请求结果？
    - [x] **前置 9.P2** 看懂 effect cleanup 的 `cancelled` 和 `feedUserId` 最终校验（`product-frontend/src/pages/FeedPage.tsx:30`，`product-frontend/src/pages/FeedPage.tsx:59`）。
    - [x] **主问 9.Q2** 说明这解决的是哪一种 stale response race，而不是服务端数据一致性。
3. ⭐ `/livez` 和 `/readyz` 为什么不能合并成一个接口？
    - [x] **前置 9.P3** 对比 `build_liveness()` 与 `check_readiness()`（`backend/app/health.py:20`，`backend/app/health.py:38`）。
    - [x] **主问 9.Q3** 解释 MySQL、Kafka、outbox backlog、dead rows、worker heartbeat 分别为什么会影响 readiness。
4. ⭐ 哪些测试是真正保护核心 claim 的？
    - [x] **前置 9.P4** 找出 request split、prior counts、并发更新、outbox durable ack 和 Kafka integration 五层证据（`tests/test_train_eval_mind.py:11`，`tests/test_mysql_smoke.py:133`，`tests/test_outbox_mysql.py:82`，`tests/test_kafka_integration.py:32`）。
    - [x] **主问 9.Q4** 解释为什么 unit、MySQL integration、Kafka integration 被拆成不同 CI job（`.github/workflows/ci.yml:8`，`.github/workflows/ci.yml:37`，`.github/workflows/ci.yml:69`）。
5. ⭐ 90 秒项目故事怎样既有技术含量又不夸大？
    - [x] **前置 9.P5** 串起“公开 MIND impression → 时间安全评估 → 多源召回 → LightGBM 排序 → 事件画像更新 → Outbox/Kafka”。
    - [x] **主问 9.Q5** 用六句话讲 problem、data、design、correctness、evidence、limitation，并准备回答“为什么 ALS 没提升还保留”“为什么搜索不能说有效”“为什么不是生产系统”。

> 带读笔记（已讨论）
>
> - 关于 impression identity 的当前理解：`trackedRef` 用 `(user_id, request_id, article_id)` 标识一次具体 feed 曝光；同一组合的 effect 重跑需要去重，但换用户或换 feed request 后同一文章应重新计为曝光。
> - 可复用模式：前端去重键应对应业务事件 identity，而不是只选最显眼的实体 ID。
> - trade-off：复合 key 更准确，但 `Set` 只在当前页面实例内存中有效；跨刷新可靠幂等仍依赖服务端 `event_id`。
> - 关于 impression 重试的当前理解：key 在请求发出前加入 `trackedRef`，防止 in-flight 重复发送；若 Promise rejected，则删除对应 key，让后续 effect 可以重新上报。
> - 可复用模式：客户端去重状态应区分“正在提交/已成功”和“提交失败”，失败不能永久占用幂等槽位。
> - trade-off：失败后自动重试可能产生重复请求，但服务端 event ID 幂等可兜底；不重试则会形成不可恢复的曝光漏记。
> - 关于 persona 切换保护的当前理解：effect cleanup 把旧请求闭包标记为 `cancelled`，阻止其回写 state；`feedUserId` 再确保渲染和曝光上报的数据确实属于当前 persona。
> - 可复用模式：异步 UI 同时使用“请求生命周期失效标记”和“响应身份校验”，防止乱序结果污染当前视图。
> - trade-off：逻辑忽略旧响应但未真正中止网络请求；若需节省带宽可使用 AbortController，同时仍保留身份校验。
> - 关于前端 stale response 的当前理解：Alice 的慢请求可能晚于 Bob 的快请求返回；cleanup 阻止 Alice 旧响应覆盖当前 state，`feedUserId` 防止错误 persona 的数据被展示或上报。
> - 可复用模式：前端只接受“仍属于当前交互上下文”的异步结果；这与服务端事务、数据库锁和消息一致性是不同层次的问题。
> - trade-off：前端防竞态保证视图正确，但不会撤销服务端已完成的读取，也不解决服务端数据本身的并发写问题。
> - 关于健康检查的当前理解：liveness 只回答应用进程是否还活着；readiness 检查真实依赖与积压状态，回答该实例现在是否适合继续接流量。
> - 可复用模式：把“需要重启”和“暂时摘流量”拆成两个信号，避免依赖短暂故障触发无意义的重启循环。
> - trade-off：readiness 检查越完整越能保护用户，但检查过慢或阈值过严会造成实例频繁摘流量。
> - 关于 readiness 依赖的当前理解：MySQL 失败破坏核心读写，Kafka 失败阻断事件流，outbox backlog/oldest/dead 暴露投递异常，worker heartbeat 与 lag 暴露后台处理停摆。
> - 可复用模式：readiness 不只检查端口连通，还检查系统是否有能力持续兑现对用户承诺的完整业务闭环。
> - trade-off：将异步链路纳入 readiness 能尽早止损，但也可能因后台故障让仍可读的接口一起摘流量，需要按产品降级策略决定阈值。
> - 关于测试分层的当前理解：request split 与 prior counts 用纯逻辑测试守住离线时间正确性；并发 click 用真实 MySQL 验证锁；durable ACK 验证 outbox 已落盘；Kafka integration 验证消息端到端到达 MySQL 与 training topic。
> - 可复用模式：每个关键承诺都选择能观察该故障的最低成本测试层，不用 mock 测试冒充真实基础设施证据。
> - trade-off：越接近端到端越真实但越慢、越易受环境影响；纯单测快但无法证明数据库锁和 broker 行为。
> - 关于 CI job 拆分的当前理解：quality job 提供快速 lint/type/unit/frontend 反馈；MySQL job验证真实 SQL、事务和锁；Kafka job单独启动 broker，验证最昂贵的消息链路。
> - 可复用模式：按基础设施边界拆 CI，使快速反馈、环境准备、失败定位和重跑成本彼此独立。
> - trade-off：拆 job 可并行且易诊断，但会重复 checkout/安装依赖；可用缓存缓解，不能为了省几分钟把不同故障域混成一团。
> - 关于项目主链的当前理解：公开 MIND impressions 经规范化与时间安全评估形成离线证据；线上采用多源召回与 LightGBM 排序；用户事件通过 Outbox/Kafka 幂等更新画像，反馈到下一次 feed。
> - 可复用模式：把离线训练证据、在线 serving 路径和行为反馈闭环分层，再用明确契约连接，而不是把训练脚本直接当线上系统。
> - trade-off：分层提高可验证性和演进空间，但离线 artifact、在线特征公式和事件语义必须持续做契约校验。
> - 关于六句项目介绍的当前理解：按 problem、data、design、correctness、evidence、limitation 组织；明确 LightGBM 超过已测 baseline、ALS 未带来可测增益，搜索仅有机制证据，系统仍是公开数据驱动的原型。
> - 可复用模式：项目介绍同时给出正向成果、反例结果和证据边界，比只罗列组件更能体现工程判断。
> - trade-off：诚实说明局限会降低夸张冲击力，但能提前化解“ALS 为什么保留”“搜索是否有效”“是否生产系统”等高压追问。
> - 还没展开的问题：§9 已完成；返回前面尚未完成的章节继续 DFS。

## 10. 明日高压模拟：12 个 new-grad 搜索 / 推荐面试场景

> **使用方法**：先遮住“合格回答”，只看主问并开口说 60 秒；再回答连续追问。  
> **统一答题骨架**：①名词是什么；②本项目怎么做；③为什么这样做、代价是什么；④证据能证明什么、不能证明什么。  
> **广告边界**：本项目主线是新闻搜索与推荐。广告只做概念迁移，不能包装成已经实现的竞价、预算或投放系统。

### 场景 1/12：`N123-0` 是什么负样本？

**名词先说人话**

- **Impression / 曝光**：系统真的把一组新闻摆到用户面前。
- **Candidate / 候选**：这次曝光列表中的一篇新闻。
- **Exposed non-click / 曝光未点击**：用户有机会看到，但没有点击。
- **Random negative / 随机负样本**：从全库随便抽一篇“没观察到点击”的新闻；它可能根本没展示过。

**项目到底干了什么**

MIND 的 `N123-0` 会被解析成 `article_id=123, clicked=False`。归一化 manifest 明确把负样本定义为 `exposed candidate with clicked=false`，没有把全库未点击内容伪造成同等语义的负例。

**面试官主问**

> **面试官：** 为什么曝光未点击通常比全库随机负样本更适合训练排序模型？

**new-grad 常见错误回答**

> **候选人（错误）：** 标签都是 0，所以两种负样本对模型没有区别。

错在只看数值，没看数据是怎么产生的。曝光未点击与正例参与过同一屏竞争，通常更难；随机负样本往往离用户兴趣很远，模型容易刷出虚高离线分。

**连续追问**

1. `0` 能不能直接解释成“用户讨厌这篇文章”？
2. 曝光未点击里可能混入哪些噪声，例如位置太靠后或用户没看见？
3. 如果只能拿到随机负样本，你会怎样减少训练分布与线上候选分布的偏差？
4. 广告场景里，未点击曝光与未参与竞价的广告能不能当成同一种负例？

**合格回答（60 秒）**

> **候选人（合格）：** 曝光未点击表示内容真实进入过用户的选择集合，随机未点击只表示日志里没有观察到点击。这个项目直接解析 MIND impression 中的 `0/1` 标签，并在 provenance 中记录负样本是曝光候选。好处是训练更贴近线上同屏排序；代价是未点击不等于明确不喜欢，还会受位置和注意力偏差影响。它能支持 impression-aware 的离线排序比较，但**不能证明标签无噪声，也不能证明线上 CTR 会提升**。

**项目证据**

- `backend/app/data_contracts/mind.py:111-122`
- `scripts/normalize_mind.py:275-287`
- `scripts/normalize_mind.py:369-379`

**记忆口诀**

> **见过没点，比随机更难；没点不等于讨厌。**

**开口验收**

- 60 秒不看答案说明 exposed non-click 与 random negative 的区别。
- 陷阱题：面试官说“都是 label=0”，你必须先反问或解释它们的生成机制。

### 场景 2/12：为什么按时间切完整 request，而不是随机切 item？

**名词先说人话**

- **Request-level split**：同一次曝光请求的所有候选一起进 train 或 test。
- **Chronological split**：早发生的请求训练，晚发生的请求测试。
- **Target leakage / 标签泄漏**：特征里偷偷混入当前或未来的答案。
- **Prior count**：只统计当前请求发生之前的曝光与点击。
- **Offline / online skew**：离线能拿到某个信息，线上真正打分时却拿不到。

**项目到底干了什么**

项目先按 `event_ts` 排 request，用 `< cutoff` 和 `>= cutoff` 切分；相同时间戳不会被劈开。热度特征先读取历史计数，再把当前曝光和点击写回，避免当前 label 进入自己的特征。

**面试官主问**

> **面试官：** 随机切 item 数据更多、分布也更均匀，为什么这里还坚持全局时间切 request？

**new-grad 常见错误回答**

> **候选人（错误）：** 只要训练集和测试集没有同一行，就不存在泄漏。

同一 request 的候选共享用户、时间和上下文；逐 item 随机切会让“一张考卷”横跨 train/test。若先更新当前点击计数，正样本还能直接把答案写进 hotness。

**连续追问**

1. 为什么相同 timestamp 的 request 要留在同一侧？
2. 如果先 `click_count += clicked`，再生成特征，会发生什么？
3. `article_age_hours` 为什么只能叫数据窗口内 age，而不是新闻发布时间？
4. 时间切分的代价是什么，为什么 train ratio 可能不精确？
5. 广告训练里，未来转化或预算状态混进历史特征属于什么问题？

**合格回答（60 秒）**

> **候选人（合格）：** 推荐线上是“用过去预测未来”，所以评估单位应是完整曝光 request，并按全局时间边界切分。项目保证同 timestamp 请求不跨分区，构造热度时也先读 prior count、后更新当前行为。这样减少同请求共享上下文和当前标签泄漏；代价是时间边界可能牺牲精确样本比例，也更容易暴露真实的分布漂移。它证明评估顺序更接近线上，**不证明线上数据完全无偏，也不证明所有未来特征都已被排除**。

**项目证据**

- `scripts/train_eval_mind.py:35-46`
- `scripts/train_eval_mind.py:130-140`
- `tests/test_train_eval_mind.py:8-55`

**记忆口诀**

> **整张考卷一起切；先读历史，再写现在。**

**开口验收**

- 说清 request-level、time split、prior count 三者分别防什么。
- 陷阱题：面试官说“没有重复 row 就安全”，你要指出共享 request 上下文与当前 label 泄漏。

### 场景 3/12：Recall、NDCG、MRR、Diversity 到底各看什么？

**名词先说人话**

- **Recall@K**：该找的好内容，前 K 找全了多少。
- **NDCG@K**：好内容有没有排前；越靠后贡献越小。
- **MRR**：每个请求第一个好结果来得多快。
- **Category Diversity@K**：前 K 覆盖多少不同类目，避免列表过于单一。
- **Primary metric**：主要优化目标；**guardrail**：防止优化主指标时伤害其他体验。

**项目到底干了什么**

代码按 `request_id` 分组计算四类指标。当前 LightGBM Recall@10 为 `0.5969`，ALS-adjusted 为 `0.5967`；ALS candidate Recall@50 只有 `0.0262`。这些都是离线 MIND 证据。

**面试官主问**

> **面试官：** 新闻排序应该选哪个主指标？如果 Recall 高但 NDCG 低，你怎么解释？

**new-grad 常见错误回答**

> **候选人（错误）：** Recall 最高的模型就是最好的，因为找回得最多。

Recall 不关心前 K 内顺序，也不直接衡量列表是否单一。高 Recall、低 NDCG 常表示“好内容进来了，但排得靠后”。

**连续追问**

1. MRR 高、Recall 低说明什么？
2. Diversity 高、NDCG 低能不能说体验更好？
3. 为什么新闻 feed 常用 NDCG 做主指标、Recall 和 Diversity 做 guardrail？
4. LightGBM 与 ALS-adjusted 数字接近时，能不能声称 ALS 提升？
5. 离线 Recall@10 能不能直接翻译成 CTR 提升百分比？

**合格回答（60 秒）**

> **候选人（合格）：** 我用“找全、排前、首中、不单一”区分四个指标。新闻排序可把 NDCG 作为主指标，因为位置影响曝光；Recall 检查候选覆盖，MRR补充首个满意结果，Diversity 防列表过窄。项目中 LightGBM 超过已测 baseline，但加入 ALS 后 `0.5969 → 0.5967`，所以我把 ALS 讲成负结果而不是增益。离线指标能比较当前 replay 下的方案，**不能证明线上 CTR、长期满意度或因果收益**。

**项目证据**

- `scripts/train_eval_mind.py:291-340`
- `docs/metrics.md:8-30`

**记忆口诀**

> **Recall 找全，NDCG 排前，MRR 首中，Diversity 不单一。**

**开口验收**

- 不算公式，只用四个真实故障场景选指标。
- 陷阱题：高 MRR 不代表多正例都被找回；高 Diversity 不代表相关。

### 场景 4/12：热门内容一直推，用户真正想要的内容上不来，怎么解决？

**名词先说人话**

- **Candidate pool / 候选池**：排序前先捞出来的一批内容。
- **Recall failure**：目标内容根本没进候选池。
- **Ranking failure**：目标内容已进候选池，但分数不够高。
- **Popularity bias / 热门偏置**：热门内容因历史行为多而持续获得更多曝光。
- **Feedback loop / 反馈回路**：多曝光带来多点击，多点击又带来更多曝光。
- **Source attribution**：记录候选来自画像、搜索、ALS 还是热门兜底。

**项目到底干了什么**

项目按画像 topic、最近搜索 topic、ALS 多路召回，主候选不够才补 hot/fresh。候选按 article ID 去重并保留来源；热度使用点击和曝光计数，排序还会加入个性化 topic 与 query boost。

**面试官主问**

> **面试官：** 热门新闻一直霸榜，你会怎么定位和修复？

**new-grad 常见错误回答**

> **候选人（错误）：** 直接删除 popularity 特征，热门偏置就消失了。

这可能让冷用户无内容可看，也没回答目标内容究竟“没召回”还是“召回后没排前”。

**连续追问**

1. 你第一张 debug 表会看哪些字段？
2. 目标内容没进候选池，应该改召回还是改 ranker？
3. 目标内容已进入但排在第 100，应该检查哪些特征？
4. 如何避免去热门后伤害冷启动可用性？
5. 你会用哪些离线与线上 guardrail 防止另一个极端？

**合格回答（60 秒）**

> **候选人（合格）：** 我先用 article 是否进入候选池和 `sources` 区分 recall failure 与 ranking failure。没进池就查画像、最近搜索、ALS 的覆盖与过滤；进池但靠后就看 hotness、topic match、query boost 和模型分数贡献。当前代码已支持多路来源、去重和“主召回不足才热门兜底”。进一步可实验热度归一化或上限、召回配额、探索与多样性 rerank，但要保留冷启动 fallback。这个诊断能定位漏斗阶段，**不能仅凭离线分数证明反馈回路已在线上消除**。

**项目证据**

- `backend/app/repositories/mysql.py:1392-1480`
- `backend/app/repositories/_utils.py:99-115`
- `backend/app/repositories/content_dao.py:71-115`
- `backend/app/repositories/mysql.py:298-358`

**记忆口诀**

> **先看进没进，再看排第几；热门兜底不能变热门霸榜。**

**开口验收**

- 60 秒必须按“诊断 → 召回修复 → 排序修复 → guardrail → 验证”回答。
- 陷阱题：删除热门特征不是第一步；先定位漏斗阶段。

### 场景 5/12：ALS 矩阵中的 1 和 0 分别代表什么？

**名词先说人话**

- **ALS**：把用户和文章学成向量，让点积高的组合更匹配。
- **User-item matrix**：行是用户，列是文章。
- **CSR sparse matrix**：只存少量非零格子的稀疏矩阵。
- **Implicit feedback**：点击暗示兴趣，但不是用户明确打分。
- **Confidence weighting**：让重复点击、停留时长等强信号权重更高。

**项目到底干了什么**

代码只取 clicked rows，把每个 `(user, article)` 非零位置统一填成 `1`，再训练 ALS。这里没有按次数、停留时长或时间衰减设置不同 confidence。

**面试官主问**

> **面试官：** 这张矩阵里的 `1` 是评分 1 分吗？`0` 是明确不喜欢吗？

**new-grad 常见错误回答**

> **候选人（错误）：** 是的，1 是喜欢，0 是不喜欢，所以这是标准二分类标签。

点击只是隐式正反馈；0 通常表示“没观察到交互”，可能是没曝光、没注意或没兴趣。

**连续追问**

1. 为什么用稀疏矩阵，而不是完整二维数组？
2. 一次误点和十次点击都填 1，会损失什么？
3. 曝光未点击应该怎样进入 implicit ALS，能否直接当强负例？
4. 加 confidence weighting 可能带来什么新偏差？

**合格回答（60 秒）**

> **候选人（合格）：** ALS 输入是 user-item 稀疏交互矩阵，项目把观察到的点击统一记成 1；它是 implicit positive，不是 1 分评分。0 只代表没有观察到点击，不能直接解释为讨厌。二值实现简单、数据契约清楚，但压平了误点、重复点击和强兴趣；后续可用次数、停留或时间衰减构造 confidence，同时注意热门用户和热门 item 会获得更大权重。它证明代码利用了协同点击关系，**不能证明矩阵中的缺失值是真负例**。

**项目证据**

- `scripts/train_eval_mind.py:185-218`
- `scripts/train_eval_mind.py:202`

**记忆口诀**

> **1 是看见点击，0 是没有证据；缺失不等于差评。**

**开口验收**

- 用“行、列、非零值、零值”四句话解释矩阵。
- 陷阱题：面试官把 implicit feedback 说成评分数据时，必须纠正。

### 场景 6/12：`IndexFlatIP` 为什么不能直接说是 cosine？

**名词先说人话**

- **Embedding**：把用户或文章压成一串数字坐标。
- **Inner product / 点积**：既受向量方向，也受向量长度影响。
- **Cosine similarity**：主要比较方向；通常先把向量长度归一成 1。
- **L2 normalization**：只缩放长度，不改变方向。
- **Artifact**：模型、embedding、FAISS index、ID map、metadata 等离线产物。
- **Version skew**：相关文件来自不同版本，彼此对不上。

**项目到底干了什么**

项目把未归一化 ALS item factors 放进 `IndexFlatIP`，metadata 写明 `inner_product`。线上只有整套 artifact 存在且相似度匹配才加载；FAISS 内部位置再由 ID map 翻译成真实 article ID。

**面试官主问**

> **面试官：** 为什么这里叫 inner product，而不是 cosine？只更新 FAISS index、不更新 ID map 会怎样？

**new-grad 常见错误回答**

> **候选人（错误）：** `IndexFlatIP` 会自动归一化，而且 index 本身保存了真实 article ID。

FAISS 不会自动做 L2 normalize；这里返回的是内部位置，真实 ID 依赖同版本 map。

**连续追问**

1. 两边都归一化后，IP 与 cosine 有什么关系？
2. 为什么 cosine 不一定比 raw IP 更好？
3. 向量长度可能携带什么信号？
4. mtime signature 能解决什么，不能解决什么？
5. 如何更稳妥地发布多文件模型版本？

**合格回答（60 秒）**

> **候选人（合格）：** `IndexFlatIP` 计算 raw inner product，代码没有 L2 normalize，所以分数同时受方向和长度影响，不能叫 cosine。ALS 原始打分也是 user/item dot product，因此 IP 与训练目标更一致；改 cosine 会删除模长信号，是否更好要做 ablation。线上还必须把 index、embedding、ID map 和 metadata 当成同一版本，否则可能检索到 A 的向量却返回 B 的 ID。当前完整性与 mtime 检查能发现缺文件或变化，**不能单独保证多文件原子发布**。

**项目证据**

- `scripts/train_eval_mind.py:219-257`
- `backend/app/repositories/als_recall.py:34-67`
- `backend/app/repositories/als_recall.py:73-94`

**记忆口诀**

> **IP 看方向加长度；cos 只看方向；索引号必须配地图。**

**开口验收**

- 用“箭头方向与长度”类比讲清 IP / cosine。
- 陷阱题：`IndexFlatIP` 不会自动 normalize，FAISS position 也不等于 article ID。

### 场景 7/12：ALS 很弱、冷用户又没向量，为什么还保留这条通道？

**名词先说人话**

- **Cold start**：新用户没有足够历史，协同模型没有 user embedding。
- **Fallback channel**：主通道没证据时，用内容、类目、热门或新鲜内容兜底。
- **Candidate Recall@50**：从全库召回 50 篇时，找回真实正例的比例。
- **Feature parity**：训练和服务使用相同特征含义、名称和顺序。
- **Fail closed**：模型契约不兼容时拒绝使用，而不是悄悄猜。

**项目到底干了什么**

ALS 对未加载模型或 unknown user 返回 `[]`，上游再用内容 / 类目 / hot fallback。当前 ALS candidate Recall@50 为 `0.0262`，且 ALS-adjusted 没超过 LightGBM。LightGBM 加载时严格检查 feature schema 和列顺序。

**面试官主问**

> **面试官：** ALS 效果这么差，为什么不马上删掉？冷用户为什么不用平均向量？

**new-grad 常见错误回答**

> **候选人（错误）：** 保留就说明线上一定有价值；冷用户用平均向量至少能返回结果。

当前证据恰好没有显示 ALS 增益。平均向量会把热门偏置伪装成协同个性化，还模糊候选来源。

**连续追问**

1. 什么条件下保留研究通道，什么条件下生产下线？
2. 为什么 `[]` 比 success-shaped fake vector 更诚实？
3. unknown user 被跳过时，为什么必须另报 coverage？
4. 特征列顺序错了，模型为什么可能“能跑但跑错”？
5. 显式 LGB 实验 arm 与默认手工公式降级为何应有不同失败语义？

**合格回答（60 秒）**

> **候选人（合格）：** 当前 ALS 是可插拔研究通道，不是已证明的收益点。它的 all-catalog Recall@50 只有 `0.0262`，混入 LightGBM 后也没有提升；因此生产是否启用要看增量收益是否覆盖 artifact、延迟和运维成本。冷用户没有协同证据就返回空，让内容和热门 fallback 以明确来源接管，而不是伪造平均向量。LightGBM 侧再用 schema 与列顺序保护 online/offline parity。现有结果支持“架构可插拔且 fallback 可用”，**不支持声称 ALS 已改善推荐**。

**项目证据**

- `backend/app/repositories/als_recall.py:73-94`
- `backend/app/repositories/mysql.py:1432-1480`
- `backend/app/repositories/ranker.py:26-70`
- `backend/app/repositories/ranker.py:79-96`
- `docs/metrics.md:17-26`

**记忆口诀**

> **没证据就空；弱通道可插拔；特征必须同名同序。**

**开口验收**

- 回答必须同时讲研究价值、生产成本和下线条件。
- 陷阱题：保留代码不等于证明有效；unknown-user 指标不能混成 known-user ALS 指标。

### 场景 8/12：用户输入文字，怎么变成内部 `query_key`？

**名词先说人话**

- **Display query**：用户看见并输入的文字。
- **Query key**：系统内部稳定使用的查询标识。
- **Resolver**：把外部文字翻译成内部标识的解析器。
- **Lexical match**：按字面文本匹配 headline / abstract。
- **422 Unprocessable Entity**：请求格式合法，但业务语义无法解析。
- **Fail closed**：不知道就明确报错，不编造一个看似成功的结果。

**项目到底干了什么**

解析链是：numeric key 直通 → `display_query` → topic 展示名 → article headline / abstract 文本匹配；都失败就抛 `UnresolvedQueryError`，API 返回 422。

**面试官主问**

> **面试官：** 为什么未知 query 不直接 hash 成一个新 key，或者返回空列表 200？

**new-grad 常见错误回答**

> **候选人（错误）：** 搜不到就返回空数组，接口成功最重要。

空成功会把“解析器不认识 query”伪装成“系统认识 query，但库里没有结果”，还可能写入无法解释的画像信号。

**连续追问**

1. numeric fast path 解决什么问题？
2. display query、topic name、article text 三层 fallback 的精度有什么差别？
3. lexical match 会有哪些误匹配？
4. 为什么 422 比 500 更合适？
5. 如果以后接 embedding query encoder，怎样保留可调试性？

**合格回答（60 秒）**

> **候选人（合格）：** `query_key` 是后续 topic map、recent query 和 feed signal 共用的内部契约。项目优先接受稳定 numeric key，再按 display query、topic name 和 article text 逐层解析；无法解析时返回 422，而不是制造 key 或成功形状的空结果。这样保证写入画像的 query 可追踪；代价是 lexical fallback 覆盖有限，也可能需要更好的同义词或语义检索。它证明本地英文查询有确定解析路径，**不证明支持开放域搜索或所有自然语言 query**。

**项目证据**

- `backend/app/repositories/query_resolver.py:128-158`
- `backend/app/repositories/mysql.py:512-548`
- `backend/app/main.py:138-153`

**记忆口诀**

> **数字直通，文字三找；找不到就 422，不编造。**

**开口验收**

- 不看代码说出完整解析顺序。
- 陷阱题：空 200 与 unresolved 422 表达的是两种不同事实。

### 场景 9/12：一次搜索怎样影响下一次 feed？

**名词先说人话**

- **Weak intent / 弱意图**：用户搜索了某主题，但不一定真的喜欢结果。
- **Confirmation / 确认**：用户又点击搜索结果，给该 query 更强证据。
- **Overlap topic**：query topic 与被点击 article topic 的交集。
- **Decay / 衰减**：时间越久，信号权重越低。
- **Half-life / 半衰期**：经过这段时间，权重减半。
- **Gating / 门控**：满足确认条件后，signal 才能打开某条召回。

**项目到底干了什么**

`/search` 幂等写搜索事件和 recent query；搜索结果点击会确认 recent query，并让 query/article 重合 topic 获得更强 delta。feed 再把 recent query 映射成 topic score，按 legacy、decay 或 gated 配置进入召回与排序。

**面试官主问**

> **面试官：** 搜索一次就强改画像，会不会过拟合短期意图？你们怎么控制？

**new-grad 常见错误回答**

> **候选人（错误）：** 用户搜过就说明长期喜欢，下一次 feed 应全部改成这个主题。

搜索可能是一次性任务、误搜或替别人搜索。它是短期信号，不应无限期覆盖长期画像。

**连续追问**

1. 为什么搜索结果点击比单独搜索更强？
2. gated 模式为什么要求 `confirmed_ts`？
3. decay 与 gated 分别解决什么问题？
4. query signal 应只影响 ranker，还是也能打开 recall？
5. 3 个 deterministic scenario 只有 1 个改变 top-10，能得出什么结论？

**合格回答（60 秒）**

> **候选人（合格）：** 搜索是短期弱意图，点击搜索结果才是更强确认。项目把 search query 写入 recent queries；点击后记录 `confirmed_ts`，重合 topic 用更大 delta。feed 侧可以让 query signal 衰减，或在 gated 模式下只有确认后才打开召回，同时把有效 score 作为 ranking boost。这样减少一次性搜索长期污染画像；代价是门控太严会漏掉真实但未点击的意图。当前 deterministic 实验只证明链路能改变部分 demo 排序，**不证明 CTR、因果提升或真实用户收益，因为 MIND 没有搜索日志**。

**项目证据**

- `backend/app/repositories/mysql.py:512-548`
- `backend/app/repositories/mysql.py:790-815`
- `backend/app/repositories/event_dao.py:95-153`
- `backend/app/repositories/profile_dao.py:94-132`
- `backend/app/repositories/search_signal.py:11-77`
- `docs/metrics.md:27-30`

**记忆口诀**

> **搜是弱意图，点是强确认；久了衰减，没日志不谈 CTR。**

**开口验收**

- 用“search → recent query → click confirm → topic score → recall/rank”讲完整闭环。
- 陷阱题：机制接通不等于用户收益，deterministic scenario 不是 A/B test。

### 场景 10/12：重复事件、冲突事件和并发点击怎么区分？

**名词先说人话**

- **Idempotency / 幂等**：同一业务请求重试多次，最终效果仍像执行一次。
- **Event ID**：一次业务事件的唯一身份。
- **Fingerprint**：把关键业务字段算成哈希，用来判断“同 ID 是否还是同内容”。
- **Conflict**：同一个 event ID 被复用，却携带不同业务内容。
- **Row lock / 行锁**：更新画像前暂时锁住该用户行。
- **Lost update**：两个并发请求都读到旧值，后写入者覆盖前一个增量。

**项目到底干了什么**

事件先用主键 `external_event_id` 原子 claim；普通重复会回读 fingerprint 并返回 duplicate，复用 ID 但内容不同则抛冲突。画像更新读取 `user_profile ... FOR UPDATE`，并发点击测试要求两个增量都保留。

**面试官主问**

> **面试官：** 为什么唯一 event ID 还不够？为什么普通重复返回成功，冲突却返回 409？

**new-grad 常见错误回答**

> **候选人（错误）：** 数据库有唯一键，所以所有重复都应该报错；Kafka 开幂等生产者后消费端也不用幂等。

重试同一 payload 是正常分布式行为，应返回已处理语义；同 ID 换 payload 才是调用方 bug。生产者幂等也不能消除消费重放。

**连续追问**

1. fingerprint 为什么不包含 retry timestamp？
2. 同 ID、同内容与同 ID、不同 article 分别怎么处理？
3. 没有 `FOR UPDATE` 时两个 click 如何产生 lost update？
4. 行锁能不能替代 idempotency claim？
5. 冲突应该记录哪些可观测信息，又不能泄露哪些原始数据？

**合格回答（60 秒）**

> **候选人（合格）：** 幂等关注业务身份，不是“所有重复都失败”。项目用 event ID 做原子 claim，再用业务字段 fingerprint 区分重试与冲突：同 ID 同 payload 返回 duplicate success，同 ID 不同 payload 抛 `IdempotencyConflictError`，API 映射为 409。画像又是 read-modify-write，所以更新前用 `FOR UPDATE` 防两个并发增量互相覆盖。唯一键解决重复身份，行锁解决并发状态更新，二者不能互换。它能证明本地 MySQL 路径覆盖重复与并发测试，**不证明整个外部系统端到端 exactly-once**。

**项目证据**

- `backend/app/events/schema.py:84-103`
- `backend/app/repositories/event_dao.py:17-60`
- `backend/app/repositories/profile_dao.py:21-48`
- `tests/test_mysql_smoke.py:133-168`
- `backend/app/main.py:163-175`

**记忆口诀**

> **同 ID 同内容：重复成功；同 ID 换内容：409；改画像前先锁行。**

**开口验收**

- 分别回答“身份重复”和“并发覆盖”两个问题，不能混为一谈。
- 陷阱题：Kafka producer idempotence 不等于 consumer 或 DB exactly-once。

### 场景 11/12：Transactional Outbox 为什么仍是 at-least-once？

**名词先说人话**

- **Dual write / 双写**：一次业务同时写数据库和发 Kafka。
- **Transactional Outbox**：业务数据与待发送消息先写进同一个数据库事务。
- **At-least-once**：消息保证至少送达一次，可能重复。
- **`SKIP LOCKED`**：多个 worker 抢任务时，跳过已被别人锁住的行。
- **Stale claim**：worker 抢到任务后崩溃，行长期停在 publishing。
- **Backoff / 退避**：失败后逐步延长重试间隔。
- **DLQ**：无法解析的坏消息进入死信队列，避免无限重试。
- **Readiness**：实例是否适合接流量，不只是进程是否活着。

**项目到底干了什么**

业务事务内写 outbox；publisher 用 `FOR UPDATE SKIP LOCKED` claim batch，发送成功后标记 published，失败则退避或 dead，陈旧 claim 可恢复。consumer 对坏消息发 DLQ 并提交 offset，对暂时错误重试。readiness 检查 MySQL、Kafka、outbox backlog/dead row、worker heartbeat 与 lag。

**面试官主问**

> **面试官：** Outbox 是否实现了 exactly-once？如果 Kafka 已发送成功，但进程在标记 published 前崩溃会怎样？

**new-grad 常见错误回答**

> **候选人（错误）：** 消息和业务数据在一个事务里，所以 Kafka 也 exactly-once。

数据库事务只保证 outbox row 与业务状态一致；Kafka 发送和“标记 published”之间仍有崩溃窗口，恢复后可能重发。

**连续追问**

1. “先 commit MySQL 再发 Kafka”与“先发 Kafka 再 commit”分别会丢什么？
2. 多个 publisher 为什么不会同时处理同一批行？
3. stale publishing 行怎么恢复？
4. 无效消息与暂时性数据库错误为何采用不同策略？
5. 为什么 consumer 仍要复用幂等 claim？

**合格回答（60 秒）**

> **候选人（合格）：** Outbox 把不可原子完成的 DB+Kafka 双写，变成“同一 DB 事务写业务状态和待发送消息”，再异步投递。项目用 `SKIP LOCKED` 并发 claim，失败退避、超过次数转 dead，并恢复 stale claim。发送成功但标记前崩溃会导致重发，所以语义仍是 at-least-once，consumer 必须幂等。坏 payload 进 DLQ，暂时错误重试；readiness 还会把 backlog、dead row、heartbeat 和 lag 纳入判断。它提高了不丢消息的可靠性，**不证明端到端 exactly-once 或生产规模容量**。

**项目证据**

- `backend/app/events/consumer.py:68-96`
- `backend/app/events/outbox.py:34-79`
- `backend/app/events/outbox.py:84-153`
- `backend/app/events/outbox.py:181-208`
- `backend/app/events/consumer.py:452-504`
- `backend/app/health.py:60-159`

**记忆口诀**

> **先同库落单，再异步送；可以重复，不能丢；消费仍幂等。**

**开口验收**

- 必须主动说出“发成功、标记前崩溃”的重复窗口。
- 陷阱题：Outbox 解决双写丢失，不自动消灭重复。

### 场景 12/12：90 秒项目故事怎样既像工程项目，又不吹成生产 Ads 系统？

**名词先说人话**

- **Problem**：要解决的用户或系统问题。
- **Data**：你实际拥有的数据语义与限制。
- **Design**：召回、排序、状态更新与可靠性方案。
- **Correctness**：怎样防泄漏、重复、并发覆盖与消息丢失。
- **Evidence**：代码、测试和指标真正支持的结论。
- **Limitation**：尚未证明、没有数据或不属于项目的部分。
- **Production-scale**：需要真实容量、稳定性和运行证据，不是技术栈多就算。

**项目到底干了什么**

这是基于公开 MIND 的新闻推荐系统：真实 impression-aware 数据、时间安全评估、多源召回、LightGBM 排序、搜索反馈机制、MySQL 状态、Outbox/Kafka 与分层测试。当前证据也明确保留 ALS 负结果、搜索无真实日志和本地延迟边界。

**面试官主问**

> **面试官：** 请用 90 秒介绍项目。为什么 ALS 没提升还保留？搜索是否有效？这是不是生产级或广告系统？

**new-grad 常见错误回答**

> **候选人（错误）：** 我用了 FastAPI、MySQL、Kafka、FAISS、ALS 和 LightGBM，Recall 达到 59.69%，证明线上 CTR 提升；架构也可以直接叫 Ads 平台。

这是技术栈清单，不是项目故事；`0.5969` 是 Recall@10，不是 59.69% CTR。项目也没有广告竞价、预算与 pacing 证据。

**连续追问**

1. 你的 problem 为什么不是“我想用 Kafka 和 LightGBM”？
2. 你做了什么来保证离线指标可信？
3. 最强正结果和最重要负结果分别是什么？
4. 为什么搜索只能说机制接通，不能说有效？
5. 如果迁移到广告，除了推荐排序还缺哪些核心约束？

**合格回答（90 秒）**

> **候选人（合格）：** 我做的是一个基于公开 MIND impression 的新闻搜索与推荐闭环，目标是让离线评估、候选召回、排序和用户反馈能用一致的数据语义串起来。数据里有真实曝光、点击和曝光未点击，但没有搜索日志，所以搜索部分只做本地可验证的意图机制。系统先按用户画像、最近搜索、ALS 和热门内容多路召回，再用共享特征契约的 LightGBM 或手工公式排序；搜索和点击会更新画像。正确性上，我用全局时间 request split 和 prior-only 统计防泄漏，用幂等 claim、行锁和 Transactional Outbox 处理重试、并发与 DB/Kafka 双写。离线证据里 LightGBM Recall@10 为 `0.5969`，超过已测 baseline；ALS-adjusted 为 `0.5967`，所以 ALS 是负结果，不包装成提升。边界上，搜索实验不是 CTR 或因果证据，延迟只是本地 loopback，也不能称为生产容量。若迁移到广告，可类比“多路候选 + pCTR/质量排序”，但还必须增加 eligibility、bid、budget、pacing、frequency cap 等约束；这些不是本项目已实现的 claim。

**项目证据**

- `README.md:1-43`
- `docs/metrics.md:8-34`
- `.github/workflows/ci.yml:8-87`
- `tests/test_train_eval_mind.py:8-55`
- `tests/test_outbox_mysql.py:82-122`
- `tests/test_kafka_integration.py:28-70`

**记忆口诀**

> **问题、数据、方案、正确性、证据、边界；先讲事实，再讲限制。**

**开口验收**

- 90 秒必须出现一个正结果、一个负结果和三个边界。
- 陷阱题：Recall@10 不是 CTR；用了 Kafka 不等于生产级；能类比广告不等于做过广告系统。

## 11. 明日复习顺序

1. 先连续说三遍总口诀：**找全、排前、首中、不单一；先看进没进，再看排第几。**
2. 再练场景 4、9、12：它们最能检查你能否把召回、排序、反馈和证据边界串起来。
3. 最后练场景 10、11：只要能说清“重复 vs 冲突”“不丢但可能重复”，entry-level 系统追问就不容易崩。
4. 每题先说 60 秒，再看答案；只看懂、不出声，按未掌握处理。
