<script setup lang="ts">
import { ref } from 'vue'
import { MdPreview } from 'md-editor-v3'

defineProps<{ projectId: string }>()

const demoMarkdown = ref(`# AutoCSR · 撰写工作台占位

> M1 阶段，这里只展示 md-editor-v3 的渲染能力。
> M4 完成后，该面板会切换为 \`MdEditor\` 双栏模式，每个章节是一个文档。

## 当前里程碑：M1 骨架

- backend FastAPI :8766，已通过 \`/health\` + \`/llm/ping\` + projects CRUD
- frontend Vue 3 + Vite :5174，左/中/右三栏壳已就位
- LLM 默认使用 **DeepSeek**（\`https://api.deepseek.com/v1\`）

## 下一步（M2）

1. 实现 \`ingestion/router.py\` + 4 个 worker
2. 跑通 ICH E3 PDF 入 corpus（\`scripts/index_principles.py\`）
3. 上传 1 份 protocol.pdf + 1 份 ADSL.xpt + 1 份杂乱 Excel → 自动分流

\`\`\`python
# 等 M2 上线后，写章节 worker 会用类似如下接口
from app.llm import ark_client
from app.llm.policy import writer_llm

p = writer_llm()
out = ark_client.responses(
    [{"role": "user", "content": "Draft section 11.4.2.1..."}],
    timeout=p.timeout,
    max_tokens=p.max_tokens,
    temperature=p.temperature,
)
\`\`\`
`)
</script>

<template>
  <div class="center-editor">
    <header class="hdr">
      <span class="title">中栏 · Editor</span>
      <el-tag size="small" type="info">M1 占位</el-tag>
      <span class="meta">project id: <code>{{ projectId }}</code></span>
    </header>
    <div class="preview-wrap">
      <MdPreview :model-value="demoMarkdown" theme="light" preview-theme="github" />
    </div>
  </div>
</template>

<style scoped>
.center-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.hdr {
  padding: 12px 20px;
  border-bottom: 1px solid #e4e7ed;
  background: #fff;
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
}
.title {
  font-weight: 600;
  color: #374151;
}
.meta {
  margin-left: auto;
  font-size: 12px;
  color: #9ca3af;
}
.preview-wrap {
  flex: 1;
  overflow: auto;
  padding: 0 20px 20px;
}
</style>
