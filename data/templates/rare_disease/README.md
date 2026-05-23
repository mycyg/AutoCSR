# 罕见病 CSR 模板

适用于：孤儿药 + 罕见病 + 超罕见病 (prevalence < 1/200,000) 临床试验。

预设要点：
- 指导原则：rare_disease (ICH E3 + Rare Disease 特化)
- 设计支持：单臂 + 历史对照 / 外部对照臂 / Bayesian 自适应 / N-of-1 / 交叉设计
- 统计方法：propensity score matching、IPTW、E-value 敏感性、Bayesian 后验
- RWE 集成：注册研究 + EHR + 索赔数据；ICH E10 + FDA RWE framework
- 长期随访：OLE 阶段 + 患者年暴露统计

使用：「新建项目」下拉选「罕见病 CSR」或调 `POST /api/projects/from_sample/rare_disease`。
