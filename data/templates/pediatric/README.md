# 儿科 CSR 模板

适用于：所有儿科年龄段 (0-17 岁) 临床试验，含外推策略。

预设要点：
- 指导原则：pediatric (ICH E3 + ICH E11(R1))
- 年龄分层：早产儿 / 足月新生儿 (0-27d) / 婴幼儿 (28d-23m) / 儿童 (2-11y) / 青少年 (12-17y)
- 剂量策略：mg/kg 体重剂量 + 固定剂量分带 + PopPK 模型 (NONMEM/Monolix)
- 适口性：3/5 点 hedonic + FACES + 接受度
- 安全特化：生长 (z-score + 速度) + 发育里程碑 (ASQ/Bayley) + Tanner 分期 + 骨成熟
- 长期随访：迟发 AE + 生长轨迹 2-5 年

使用：「新建项目」下拉选「儿科 CSR」或调 `POST /api/projects/from_sample/pediatric`。
