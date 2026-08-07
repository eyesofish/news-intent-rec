# XGBoost 与 LightGBM：实现对比和项目选型

## 共同基础

XGBoost 和 LightGBM 都属于 GBDT：

- 多棵树顺序训练，而不是像 Random Forest 那样独立投票。
- 每棵新树根据当前损失产生的梯度信息修正旧模型。
- 最终模型是所有树输出的加和。

它们主要区别在于如何寻找分裂、控制模型复杂度，以及怎样降低大规模训练的
计算和内存成本。

## 论文层面的核心区别

| 维度 | XGBoost | LightGBM |
|---|---|---|
| 论文重点 | 可扩展的端到端 tree boosting 系统 | 高维、大数据 GBDT 的训练效率 |
| 优化目标 | 显式加入树复杂度正则化 | 沿用 GBDT 目标，重点减少分裂计算量 |
| 梯度信息 | 同时使用一阶梯度和二阶梯度 | 同样可使用梯度统计训练树 |
| 分裂方法 | exact greedy、近似分裂、weighted quantile sketch | histogram 将连续值离散到 bins 后寻找分裂 |
| 稀疏数据 | sparsity-aware，学习缺失值的默认分裂方向 | EFB 将几乎互斥的稀疏特征打包，减少有效特征数 |
| 样本规模 | block、cache-aware、压缩和分片等系统优化 | GOSS 保留大梯度样本并抽样小梯度样本 |
| 树生长 | XGBoost 论文中的 exact 版本主要按层生长；现代实现也支持其他策略 | 典型实现采用 leaf-wise，优先分裂收益最大的叶子 |
| 主要风险 | 参数与系统能力较多，调优和资源配置仍需实验 | leaf-wise 更激进，小数据上需用 `num_leaves`、`min_child_samples` 等防过拟合 |

两套库后来都持续演进，能力有重叠。不能把论文发表时的区别说成今天所有版本
都绝对互斥，也不能笼统声称 LightGBM 在所有数据集上都比 XGBoost 快或准。

## XGBoost 当前读到的位置

- 正则化目标同时考虑预测损失和树复杂度：
  `Omega(f) = gamma * leaf_count + 0.5 * lambda * ||leaf_weights||^2`。
- `gamma` 提高新增叶子的门槛；`lambda` 抑制过大的叶子修正值。
- `g` 是一阶梯度，表示当前修正方向；`h` 是二阶梯度，表示损失曲率。
- 一个叶子的最优输出由该叶子内的梯度统计决定：
  `w = -sum(g) / (sum(h) + lambda)`。
- 分裂只有在误差改善覆盖新增结构成本后才值得进行。
- 列采样让每棵树只看部分特征；项目的 `0.8` 是固定基线，不是已证明最优值。
- 稀疏感知分裂会为缺失当前特征的样本学习默认左右方向。
- `block` 是预先按特征列组织、排序并保留样本索引的可复用数据结构，不是
  mini-batch 或树节点。
- 当前停在 Section 4.1；下次从 Section 4.2 的 cache-aware access 继续。

## 为什么当前项目使用 LightGBM

### 仓库中可以直接验证的事实

1. 数据是典型结构化表格：每条候选文章样本使用固定顺序的 16 个数值特征。
2. `backend/requirements.txt` 依赖 `lightgbm>=4.0`，没有 XGBoost 依赖。
3. 离线脚本直接训练 `LGBMClassifier(objective="binary")`，并支持用
   `LGBMRanker(objective="lambdarank")` 做独立对比实验。
4. 线上 FastAPI 进程直接使用 `lightgbm.Booster` 加载原生 `.txt` artifact，
   不需要额外部署一个模型服务。
5. 当前 artifact 约 428 KB；本地记录的 LightGBM 训练耗时为 1.561 秒。
6. 当前训练证据包含 20,000 个完整训练 request、753,687 条训练样本；
   评测包含 10,000 个 request、421,431 条样本。
7. 在现有时间安全 replay 中，LightGBM 的 Recall@10 为 `0.5969`、NDCG@10
   为 `0.3628`，超过已测 popularity 和 category-profile manual baseline。

### 基于这些事实的合理选型解释

这个项目的目标是为结构化推荐特征建立一个轻量、可复现、能直接嵌入 Python
训练与服务链路的排序基线。LightGBM 同时提供分类和 learning-to-rank API，
模型 artifact 小，当前本地数据规模下训练成本低，并且已经产生了超过手工
baseline 的离线证据。因此继续使用它可以减少更换模型库、重做 artifact
格式、重新验证 online/offline 特征一致性的工程成本。

### 必须保留的证据边界

- 仓库没有在相同数据、切分和调参预算下比较 XGBoost 与 LightGBM。
- 因此不能说“实验证明 LightGBM 比 XGBoost 更好”。
- 当前代码没有显式启用 GOSS，不能把 GOSS 的论文收益说成项目已实现收益。
- 当前代码也没有单独测量 EFB 带来的加速，不能声称项目验证了 EFB 效果。
- 已有数字只能证明 LightGBM 超过当前已测 baseline，不能证明线上 CTR 提升。

## 面试回答

> XGBoost 和 LightGBM 都是 GBDT 的工程化实现。XGBoost 的论文重点是正则化
> 目标、二阶梯度、稀疏感知和可扩展系统设计；LightGBM 进一步用 histogram、
> leaf-wise、GOSS 和 EFB 降低大规模训练成本。我的项目使用 LightGBM，主要
> 是因为输入是 16 个结构化推荐特征，Python 训练脚本和 FastAPI 服务可以直接
> 复用同一套 LightGBM artifact 与特征契约，而且当前离线 replay 中它明显超过
> 已测手工 baseline。这个选择是务实的工程基线，不是因为我做过 XGBoost
> 对照并证明 LightGBM 必然更优；如果要严谨比较，我会固定数据切分、特征、
> 计算预算和主指标 NDCG@10，再做同条件实验。
