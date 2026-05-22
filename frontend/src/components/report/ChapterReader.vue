<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import type { SectionDraftDTO } from '@/api/rest'

const props = defineProps<{
  projectId: string
  nodeId: string | null
  draft: SectionDraftDTO | null
  outlineTitle?: string
}>()

const emit = defineEmits<{
  (e: 'regenerate', extra?: string): Promise<void> | void
}>()

const showExtra = ref(false)
const extraInstruction = ref('')

const empty = computed(() => !props.draft)

async function onRegenerate(): Promise<void> {
  if (!props.nodeId) return
  try {
    await ElMessageBox.confirm(
      '会调用 writer agent 重新生成本节，覆盖现有草稿（旧版本不会保留）。',
      '重写本节',
      { type: 'warning' },
    )
  } catch {
    return
  }
  await emit('regenerate', extraInstruction.value || undefined)
  extraInstruction.value = ''
  showExtra.value = false
}

async function onCopy(): Promise<void> {
  if (!props.draft) return
  try {
    await navigator.clipboard.writeText(props.draft.markdown)
    ElMessage.success('Markdown 已复制')
  } catch {
    ElMessage.error('复制失败，请手动选取')
  }
}
</script>

<template>
  <div class="chapter-reader">
    <div v-if="empty" class="empty">
      <p v-if="nodeId">本节尚无草稿。</p>
      <p v-else>← 在左侧选择章节</p>
      <el-button v-if="nodeId" type="primary" plain size="small" @click="onRegenerate">
        生成本节
      </el-button>
    </div>
    <template v-else-if="draft">
      <div class="toolbar">
        <span class="title">{{ draft.title || outlineTitle || draft.node_id }}</span>
        <span class="meta">
          <el-tag size="small" :type="draft.status === 'error' ? 'danger'
                                       : draft.status === 'harmonized' ? 'success' : 'info'">
            {{ draft.status }}
          </el-tag>
          <span class="words">{{ draft.word_count }} 字</span>
          <span class="tokens">tok in {{ draft.llm_meta.tokens_in }} / out {{ draft.llm_meta.tokens_out }}</span>
        </span>
        <span class="spacer" />
        <el-button size="small" plain @click="showExtra = !showExtra">
          {{ showExtra ? '收起' : '+ 指令' }}
        </el-button>
        <el-button size="small" type="primary" plain @click="onRegenerate">重写本节</el-button>
        <el-button size="small" @click="onCopy">复制 Markdown</el-button>
      </div>
      <div v-if="showExtra" class="extra">
        <el-input v-model="extraInstruction" type="textarea" :rows="2"
                  placeholder="给 writer 一些额外说明（例：聚焦在安全性叙事；引用 ADAE 表）" />
      </div>
      <div v-if="draft.warnings?.length" class="warnings">
        <el-alert type="warning" :closable="false">
          <ul class="warn-list">
            <li v-for="w in draft.warnings" :key="w">{{ w }}</li>
          </ul>
        </el-alert>
      </div>
      <MdPreview class="md" :model-value="draft.markdown" :preview-theme="'github'" />
      <div v-if="draft.citations?.length" class="cites">
        <h4>引用</h4>
        <ul>
          <li v-for="c in draft.citations" :key="c.ref_code">
            <code>{{ c.ref_code }}</code>
            <span class="cite-type">[{{ c.type }}]</span>
            <span class="cite-snippet">{{ c.snippet }}</span>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chapter-reader { height: 100%; display: flex; flex-direction: column; }
.empty { padding: 80px 0; text-align: center; color: #9ca3af; }
.toolbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 12px; border-bottom: 1px solid #e5e7eb; background: #fff;
}
.toolbar .title { font-weight: 600; color: #111827; }
.toolbar .meta { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: #6b7280; }
.toolbar .words { font-family: ui-monospace, monospace; }
.toolbar .tokens { font-family: ui-monospace, monospace; }
.toolbar .spacer { flex: 1; }
.extra { padding: 8px 12px; background: #fafbfc; border-bottom: 1px solid #f3f4f6; }
.warnings { padding: 0 12px; margin-top: 8px; }
.warn-list { margin: 0; padding-left: 18px; font-size: 12px; }
.md { flex: 1; overflow: auto; padding: 0 12px; }
.cites {
  border-top: 1px solid #e5e7eb; padding: 12px;
  background: #fafbfc; max-height: 30%; overflow: auto;
}
.cites h4 { margin: 0 0 6px; font-size: 13px; color: #374151; }
.cites ul { list-style: none; padding: 0; margin: 0; font-size: 12px; }
.cites li { padding: 2px 0; }
.cite-type { color: #6b7280; margin: 0 6px; font-family: ui-monospace, monospace; }
.cite-snippet { color: #9ca3af; }
</style>
