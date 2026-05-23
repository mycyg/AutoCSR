# 肿瘤学 CSR 模板

适用于：实体瘤 + 血液肿瘤的 I/II/III 期临床试验，含免疫治疗 + 靶向治疗 + 化疗。

预设要点：
- 指导原则：oncology (ICH E3 + RECIST 1.1 + iRECIST)
- 核心章节：靶病灶选择 / 反应分类 (CR/PR/SD/PD/ORR/DCR) / 生存终点 (PFS/OS/DOR/TTP)
- 亚组分层：PD-L1 表达 / EGFR/ALK/HER2 / 既往治疗线数 / ECOG PS
- 安全性：CTCAE v5 分级 + irAE (免疫治疗) + AESI
- 必备图表：waterfall（最佳反应）/ swimmer（个体时间线）/ KM with risk table / forest plot

使用：「新建项目」下拉选「肿瘤学 CSR」或调 `POST /api/projects/from_sample/oncology` 一键带 demo 数据创建。
