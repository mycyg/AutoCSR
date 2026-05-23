# 心血管 CSR 模板

适用于：心衰 (HFrEF / HFpEF) + 急性冠脉综合征 (ACS) + 慢性 CAD + 抗血栓 试验。

预设要点：
- 指导原则：cardiovascular (ICH E3 + CV 特化)
- 主要终点：MACE 3-pt (CV death + MI + stroke) 或 4-pt (+ HF 住院)
- 事件驱动设计：events trigger analysis, not fixed N
- CEC 盲法裁决 + DSMB 监督
- 关键生物标志物：LVEF (echo/MRI/MUGA) / NT-proBNP / hs-troponin / 6MWT / NYHA class / KCCQ
- 安全亚组：出血 (BARC/TIMI/ISTH)、肾功能 (eGFR) 、高钾血症、低血压
- 复发事件分析：Andersen-Gill / LWYY 模型

使用：「新建项目」下拉选「心血管 CSR」或调 `POST /api/projects/from_sample/cardiovascular`。
