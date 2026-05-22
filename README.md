# AutoCSR — 自动临床研究报告生成系统

把临床原始数据（含杂乱真实世界数据、扫描件 CRF、手写病历）一条龙清洗成符合 ICH E3 / NMPA 指导原则的 CSR 报告。

## 数据流

```
选原则 → 上传任意形态资料 → Router 自动判型 → 子 agent 并行处理
                                                    ↓
                                            清洗工作台（LLM 提议 + 用户逐条确认）
                                                    ↓
                                            自动统计分析（StatBlock）
                                                    ↓
                                            生成大纲（按硬编码 ICH E3 模板）
                                                    ↓
                                            多 agent 并行写章节
                                                    ↓
                                            三栏 UI 对话精修
                                                    ↓
                                            导出 DOCX
```

每一步都有审计轨迹。清洗规则可导出为 `cleansing_pipeline.yaml` 复用到新批次数据。

## 目录结构

```
AutoCSR/
├── backend/      FastAPI :8766 + 所有业务模块
├── frontend/     Vue 3 + Vite + Element Plus + md-editor-v3
├── refer/        从「自动医学 PPT 项目」拷贝的只读参考代码
├── data/         运行时数据（项目文件、原则 PDF）
├── scripts/      部署、索引、压测脚本
└── docs/         设计文档
```

## 本地开发

```bash
# 后端
cd backend
python -m venv .venv && source .venv/Scripts/activate
pip install -e .
cp app/config/settings.example.yaml app/config/settings.yaml
# 编辑 settings.yaml 或设置环境变量 LLM_API_KEY
python -m uvicorn app.server.main:app --port 8766 --reload

# 前端
cd frontend
npm install
npm run dev      # http://127.0.0.1:5174（代理 API/WS 到 :8766）
```

## 复用与原创

- **直接复用**（来自 PPT 项目）：LLM 协议栈、配置加载、Dossier corpus 索引、对话编辑、三栏 UI、远端部署
- **新建**：Router agent + 并行 ingest workers、清洗工作台、临床统计、DOCX 导出、ICH E3 章节模板

设计细节见 [plan 文件](C:/Users/mycyg/.claude/plans/csr-adaptive-hedgehog.md)。
