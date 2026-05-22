# CSR 写作风格指南（AutoCSR M4）

本文件由 writer_agent 注入到每次 LLM 调用的 system prompt。文档总长须控制在 ~2KB。

## 时态约定
- **背景 / 研究依据 / 方法描述**：过去时（"研究纳入了 XX 例受试者"）。
- **结果**：过去时（"DrugA 组平均 AGE 为 ... 与 Placebo 组相比 p = ..."）。
- **讨论**：现在时与过去时混用，对既往文献评述用现在时（"既往研究表明 ..."），对本研究结果回溯用过去时。
- **结论 / 临床意义**：现在时或将来时（"本研究表明 ... 后续研究有必要 ..."）。

## 人称
- 全文避免第一人称（不出现"我们"），使用"研究者"、"申办方"或被动语态。
- 不出现"本团队"、"笔者"等口语化表达。

## 数字规范
- 百分比保留 1 位小数（"24.6%"），群体计数同时给绝对值与百分比："132 (24.6%)"。
- p 值：>= 0.001 保留 3 位小数（"p = 0.034"）；< 0.001 写作"p < 0.001"，**绝不**写"p = 0.000"。
- 置信区间统一为："95% CI: x.x to y.y"（英文 CSR）或"95% CI: x.x ~ y.y"（中文 CSR）。
- 风险比 / 优势比 / 危险比：保留 2 位小数（"HR = 0.78"）。
- 中位生存时间附加单位（"中位 OS 为 13.2 月"）。

## 缩写规则
- 首次出现写全称 + 括号缩写：「治疗紧急不良事件（treatment-emergent adverse event, TEAE）」。
- 缩写表统一放附录；正文以缩写优先复用。

## 引用风格
- 文献引用以「作者 et al. 年份」+ `[Ref<block_id>.P<page>.Col<col>.Para<para>]` 形式插入正文末。
- 统计表引用：在描述具体数字处紧跟 `[Ref<stat_id>.var<varname>]` 或整块引用 `[Ref<stat_id>]`。
- 同一段落多个引用合并到段末，按"出现顺序"排列。
- **任何数字必须能在引用的 StatBlock.markdown_table 中找到**——禁止编造。

## 表格 / 图引用
- 表格：「如表 X.Y 所示」；图：「如图 X.Y 所示」，编号 X 与所在章节号对齐。
- 表注与脚注用同一份缩写表。

## 章节起首
- 子章节正文从 H2 开始（`## ...`），不写 H1（H1 由编排器套用）。
- 每节首段 1-3 句给出本节概述，避免直接堆数字。

## 中英术语对照
| 中文 | 英文 |
|------|------|
| 受试者 | subject |
| 研究药物 | study drug / investigational product |
| 对照 | comparator / control |
| 主要终点 | primary endpoint |
| 次要终点 | secondary endpoint |
| 安全性集 | safety set |
| 全分析集 | full analysis set (FAS) |
| 符合方案集 | per-protocol set (PPS) |
| 不良事件 | adverse event (AE) |
| 严重不良事件 | serious adverse event (SAE) |
| 治疗相关不良事件 | treatment-related AE |
| 治疗紧急不良事件 | treatment-emergent AE (TEAE) |
| 退出研究 | study discontinuation |
| 风险比 | hazard ratio (HR) |
| 置信区间 | confidence interval (CI) |

## 禁忌
- 不出现"显著优于"等绝对性结论，应配 p 值与 CI 同时呈现。
- 不出现广告性词汇（"领先"、"突破"、"创新"等）。
- 不暴露受试者身份信息（姓名、详细住址、电话）。
- 不引用未在 corpus / StatBlock 中存在的 Ref 代码。
