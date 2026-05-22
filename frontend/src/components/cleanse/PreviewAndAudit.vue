<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { postPipelineYaml } from '@/api/rest'

const props = defineProps<{
  projectId: string
  fileId: string
  previewColumns: string[]
  previewRows: string[][]
  audit: { timestamp: string; action: string; file_id: string; detail: Record<string, unknown> }[]
  snapshots: { id: string; file_id: string; created_at: string; parquet_path: string }[]
  pipelineYaml: string
}>()
const emit = defineEmits<{
  (e: 'refreshPreview'): void
  (e: 'refreshYaml'): void
  (e: 'rollback', sid: string): void
}>()

const tab = ref<'preview' | 'audit' | 'pipeline'>('preview')

const previewTable = computed(() => {
  return props.previewRows.map((row) => {
    const obj: Record<string, string> = {}
    props.previewColumns.forEach((c, i) => { obj[c] = row[i] ?? '' })
    return obj
  })
})

const yamlEdit = ref('')
watch(() => props.pipelineYaml, (v) => { yamlEdit.value = v })

async function importYaml(): Promise<void> {
  if (!yamlEdit.value.trim() || !props.fileId) {
    ElMessage.warning('粘贴 YAML 并选中目标文件')
    return
  }
  try {
    const out = await postPipelineYaml(props.projectId, yamlEdit.value, props.fileId)
    ElMessage.success(`已导入 ${out.imported} 条规则到 ${props.fileId.slice(0, 8)}`)
    emit('refreshYaml')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

function copyYaml(): void {
  navigator.clipboard.writeText(props.pipelineYaml || '').then(() => {
    ElMessage.success('已复制 YAML')
  }).catch(() => { ElMessage.error('复制失败') })
}

function fmt(ts: string): string {
  try { return new Date(ts).toLocaleString('zh-CN') } catch { return ts }
}
</script>

<template>
  <div class="pa">
    <el-tabs v-model="tab" class="tabs">
      <el-tab-pane label="清洗后预览" name="preview">
        <div class="head">
          <span class="dim">前 {{ previewRows.length }} 行（清洗后 processed/）</span>
          <el-button size="small" link @click="emit('refreshPreview')">刷新</el-button>
        </div>
        <el-empty v-if="!previewColumns.length" description="尚未生成清洗后的数据"
                  :image-size="60" />
        <el-table v-else :data="previewTable" stripe size="small" class="preview-grid"
                  max-height="500">
          <el-table-column v-for="c in previewColumns" :key="c" :prop="c" :label="c"
                           min-width="120" show-overflow-tooltip />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="审计日志" name="audit">
        <el-empty v-if="!audit.length" description="还没有操作记录" :image-size="60" />
        <ul v-else class="audit-list">
          <li v-for="(e, i) in audit" :key="i" class="audit-line">
            <span class="t">{{ fmt(e.timestamp) }}</span>
            <span class="action" :class="`a-${e.action}`">{{ e.action }}</span>
            <span class="fid">{{ e.file_id ? e.file_id.slice(0, 8) : '—' }}</span>
            <span class="detail">{{ JSON.stringify(e.detail).slice(0, 120) }}</span>
          </li>
        </ul>
      </el-tab-pane>

      <el-tab-pane label="Pipeline YAML" name="pipeline">
        <div class="head">
          <span class="dim">所有已接受 / 已应用规则导出为 YAML，可在其他文件复用</span>
          <el-button size="small" link @click="emit('refreshYaml')">刷新</el-button>
          <el-button size="small" link @click="copyYaml">复制</el-button>
        </div>
        <el-input v-model="yamlEdit" type="textarea" :rows="14"
                  placeholder="规则 YAML（可粘贴外部 yaml 后点 导入）" class="yaml-edit" />
        <div class="head">
          <el-button size="small" :disabled="!fileId" @click="importYaml">
            导入到当前文件
          </el-button>
        </div>

        <div class="head">
          <span class="dim">历史快照（回滚点）</span>
        </div>
        <el-empty v-if="!snapshots.length" description="尚无快照" :image-size="60" />
        <ul v-else class="snap-list">
          <li v-for="s in snapshots" :key="s.id" class="snap-line">
            <code>{{ s.id }}</code>
            <span class="t">{{ fmt(s.created_at) }}</span>
            <el-button link size="small" type="warning" @click="emit('rollback', s.id)">
              回滚到此处
            </el-button>
          </li>
        </ul>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.pa { padding: 8px 12px; height: 100%; overflow: auto; box-sizing: border-box; }
.tabs :deep(.el-tabs__header) { margin-bottom: 6px; }
.head { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.dim { color: #6b7280; font-size: 12px; }
.preview-grid { font-size: 12px; }
.audit-list { list-style: none; padding: 0; margin: 0; font-size: 12px; }
.audit-line {
  display: flex; gap: 8px; padding: 6px 4px;
  border-bottom: 1px dashed #e5e7eb; align-items: baseline;
}
.audit-line .t { color: #9ca3af; }
.audit-line .action {
  font-weight: 500; min-width: 64px;
}
.audit-line .a-apply { color: #1d4ed8; }
.audit-line .a-rollback { color: #b45309; }
.audit-line .a-rejected { color: #b91c1c; }
.audit-line .a-accepted { color: #166534; }
.audit-line .fid { color: #6b7280; font-family: monospace; }
.audit-line .detail { color: #4b5563; flex: 1; word-break: break-all; }
.yaml-edit :deep(textarea) {
  font-family: 'JetBrains Mono', monospace; font-size: 12px;
}
.snap-list { list-style: none; padding: 0; margin: 0; font-size: 12px; }
.snap-line { display: flex; gap: 8px; padding: 4px 0; align-items: center; }
.snap-line code { background: #f3f4f6; padding: 1px 6px; border-radius: 4px; }
.snap-line .t { color: #9ca3af; }
</style>
