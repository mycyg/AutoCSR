<script setup lang="ts">
import { computed } from 'vue'
import type { FileEntryDTO, ProposalDTO } from '@/api/rest'

const props = defineProps<{
  files: FileEntryDTO[]
  proposalsByFile: Record<string, ProposalDTO[]>
  selectedFileId: string
}>()
const emit = defineEmits<{ (e: 'select', fid: string): void }>()

const TYPE_LABEL: Record<string, string> = {
  structured_data: '结构化数据',
  messy_tabular: '杂乱表格',
  pdf_form: 'PDF 表单',
  scan_crf: '扫描件',
  handwriting: '含手写',
  literature_doc: '文献/方案',
}

interface Group { type: string; label: string; files: FileEntryDTO[] }

const grouped = computed<Group[]>(() => {
  const m = new Map<string, FileEntryDTO[]>()
  for (const f of props.files) {
    const key = f.ingest_type || 'unknown'
    if (!m.has(key)) m.set(key, [])
    m.get(key)!.push(f)
  }
  return Array.from(m.entries()).map(([t, fs]) => ({
    type: t, label: TYPE_LABEL[t] || t, files: fs,
  }))
})

function counts(fid: string): { pending: number; accepted: number; rejected: number; applied: number } {
  const list = props.proposalsByFile[fid] || []
  const out = { pending: 0, accepted: 0, rejected: 0, applied: 0 }
  for (const p of list) {
    if (p.status === 'pending') out.pending++
    else if (p.status === 'accepted' || p.status === 'edited') out.accepted++
    else if (p.status === 'rejected') out.rejected++
    else if (p.status === 'applied') out.applied++
  }
  return out
}
</script>

<template>
  <div class="file-list">
    <header><h3>文件</h3></header>
    <div v-for="g in grouped" :key="g.type" class="group">
      <div class="grp-title">{{ g.label }} <span class="grp-count">({{ g.files.length }})</span></div>
      <div
        v-for="f in g.files" :key="f.file_id"
        class="file" :class="{ active: f.file_id === props.selectedFileId }"
        @click="emit('select', f.file_id)"
      >
        <div class="name">{{ f.filename }}</div>
        <div class="meta">
          <span v-if="counts(f.file_id).pending" class="pill pill-warn">待决 {{ counts(f.file_id).pending }}</span>
          <span v-if="counts(f.file_id).accepted" class="pill pill-ok">接受 {{ counts(f.file_id).accepted }}</span>
          <span v-if="counts(f.file_id).rejected" class="pill pill-no">拒绝 {{ counts(f.file_id).rejected }}</span>
          <span v-if="counts(f.file_id).applied" class="pill pill-done">已应用 {{ counts(f.file_id).applied }}</span>
        </div>
      </div>
    </div>
    <el-empty v-if="!files.length" description="没有可清洗的文件" :image-size="60" />
  </div>
</template>

<style scoped>
.file-list { padding: 12px; }
header h3 { font-size: 14px; color: #374151; margin: 4px 0 12px; }
.group { margin-bottom: 12px; }
.grp-title { font-size: 12px; color: #6b7280; padding: 4px 6px; }
.grp-count { color: #9ca3af; }
.file {
  border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px 10px;
  margin-bottom: 6px; cursor: pointer; background: #fff;
  transition: border-color 120ms ease;
}
.file:hover { border-color: #93c5fd; }
.file.active { border-color: #2563eb; background: #eff6ff; }
.name { font-size: 13px; color: #1f2937; word-break: break-all; }
.meta { margin-top: 4px; display: flex; flex-wrap: wrap; gap: 4px; }
.pill {
  display: inline-block; font-size: 11px; padding: 1px 6px; border-radius: 9px;
}
.pill-warn { background: #fef3c7; color: #92400e; }
.pill-ok   { background: #dcfce7; color: #166534; }
.pill-no   { background: #fee2e2; color: #991b1b; }
.pill-done { background: #dbeafe; color: #1e40af; }
</style>
