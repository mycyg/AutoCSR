<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useExportStore } from '@/stores/export'
import { exportDownloadUrl, type ExportOptions } from '@/api/rest'
import { connectProjectWS } from '@/api/ws'

const props = defineProps<{ id: string }>()
const exportStore = useExportStore()
let wsClose: (() => void) | null = null

const opts = ref<ExportOptions>({
  include_compliance_note: true,
  include_toc: true,
  include_appendix_cleansing: true,
  include_appendix_analysis: true,
})

onMounted(async () => {
  await exportStore.refresh(props.id)
  wsClose = connectProjectWS(props.id, (ev) => exportStore.handleWS(ev))
})

onUnmounted(() => {
  wsClose?.()
  exportStore.reset()
})

async function onExport(): Promise<void> {
  try {
    const r = await exportStore.trigger(props.id, opts.value)
    ElMessage.success(`已生成 ${r.filename} (${(r.size_bytes / 1024).toFixed(1)} KB)`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onDelete(filename: string): Promise<void> {
  try {
    await ElMessageBox.confirm(`删除 ${filename}？`, '确认', { type: 'warning' })
  } catch { return }
  await exportStore.remove(props.id, filename)
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function downloadUrl(filename: string): string {
  return exportDownloadUrl(props.id, filename)
}

function phaseToPercent(phase: string): number {
  const map: Record<string, number> = {
    starting: 5, loading_outline: 10, writing_sections: 40,
    references: 70, appendix_a: 80, appendix_b: 88, saving: 95, done: 100,
  }
  for (const k of Object.keys(map)) {
    if (phase.startsWith(k)) return map[k]
  }
  if (phase.startsWith('section:')) {
    const m = phase.match(/section:(\d+)\/(\d+)/)
    if (m) {
      const i = parseInt(m[1], 10), n = parseInt(m[2], 10)
      return Math.min(40 + Math.round((i / n) * 30), 70)
    }
    return 50
  }
  return 0
}
</script>

<template>
  <div class="export-view">
    <div class="panel">
      <h2>导出 DOCX</h2>
      <p class="hint">
        将基于当前章节草稿构建一个符合 ICH E3 排版规范的 Word 文档。
        生成完成后可在下方历史列表中下载。
      </p>
      <div class="options">
        <el-checkbox v-model="opts.include_compliance_note">
          封面合规声明（清洗 pipeline 摘要）
        </el-checkbox>
        <el-checkbox v-model="opts.include_toc">自动目录 (TOC)</el-checkbox>
        <el-checkbox v-model="opts.include_appendix_cleansing">附录 A · 清洗 pipeline</el-checkbox>
        <el-checkbox v-model="opts.include_appendix_analysis">附录 B · 分析方法</el-checkbox>
      </div>
      <div class="trigger">
        <el-button type="primary" size="large" :loading="exportStore.exporting" @click="onExport">
          {{ exportStore.exporting ? '正在生成…' : '生成 DOCX' }}
        </el-button>
        <span v-if="exportStore.exporting || exportStore.phase !== 'idle'" class="phase">
          阶段：<b>{{ exportStore.phase }}</b>
        </span>
      </div>
      <el-progress v-if="exportStore.exporting" :percentage="phaseToPercent(exportStore.phase)"
                   :indeterminate="exportStore.phase === 'starting'" :duration="2" />
    </div>

    <div class="panel">
      <h3>历史导出</h3>
      <el-table v-if="exportStore.history.length" :data="exportStore.history" size="small">
        <el-table-column prop="filename" label="文件" />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ fmtSize(row.size_bytes) }}</template>
        </el-table-column>
        <el-table-column prop="n_sections" label="章节" width="80" />
        <el-table-column prop="created_at" label="生成时间" width="200" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-link :href="downloadUrl(row.filename)" type="primary" target="_blank">下载</el-link>
            <el-button type="danger" link size="small" @click="onDelete(row.filename)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="empty">尚无历史导出。</p>
    </div>
  </div>
</template>

<style scoped>
.export-view { padding: 24px; max-width: 1100px; margin: 0 auto; }
.panel { background: #fff; border-radius: 8px; padding: 20px 24px; margin-bottom: 18px; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.panel h2 { margin: 0 0 6px 0; color: #1f2937; }
.panel h3 { margin: 0 0 12px 0; color: #1f2937; font-size: 16px; }
.hint { color: #6b7280; font-size: 13px; margin-bottom: 14px; }
.options { display: flex; flex-direction: column; gap: 6px; margin-bottom: 18px; }
.trigger { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.phase { color: #6b7280; font-size: 12px; }
.empty { color: #9ca3af; padding: 12px 0; }
</style>
