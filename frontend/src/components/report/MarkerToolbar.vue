<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  addMarker, deleteMarker, listMarkers,
  type MarkerDTO,
} from '@/api/rest'

const props = defineProps<{
  projectId: string
  nodeId: string | null
}>()

const markers = ref<MarkerDTO[]>([])

const TYPES: { type: MarkerDTO['type']; label: string; color: string }[] = [
  { type: 'risk',      label: '风险',   color: '#f56c6c' },
  { type: 'todo',      label: '待办',   color: '#409eff' },
  { type: 'question',  label: '疑问',   color: '#67c23a' },
  { type: 'important', label: '重要',   color: '#e6a23c' },
]

async function refresh(): Promise<void> {
  if (!props.nodeId) {
    markers.value = []
    return
  }
  try {
    markers.value = await listMarkers(props.projectId, props.nodeId)
  } catch {
    markers.value = []
  }
}

watch(() => props.nodeId, () => { void refresh() }, { immediate: true })

async function onAdd(type: MarkerDTO['type']): Promise<void> {
  if (!props.nodeId) return
  // Best-effort: read current selection from window
  const sel = typeof window !== 'undefined' ? window.getSelection() : null
  const text = sel?.toString() || ''
  const range: [number, number] = [0, Math.max(text.length, 1)]
  try {
    await addMarker(props.projectId, props.nodeId, type, range,
                     text ? text.slice(0, 80) : '')
    ElMessage.success(`已添加${TYPES.find(t => t.type === type)?.label}标记`)
    await refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onDelete(m: MarkerDTO): Promise<void> {
  try {
    await deleteMarker(props.projectId, m.id, m.node_id)
    await refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}
</script>

<template>
  <div class="marker-tb">
    <div v-if="!nodeId" class="empty">请先选择章节</div>
    <template v-else>
      <div class="toolbar">
        <span class="label">标记：</span>
        <button v-for="t in TYPES" :key="t.type" class="chip"
                :style="{ background: t.color }" @click="onAdd(t.type)"
                :title="`添加${t.label}标记到当前选区`">
          {{ t.label }}
        </button>
      </div>

      <div class="list">
        <div v-if="!markers.length" class="empty small">本节暂无标记</div>
        <div v-for="m in markers" :key="m.id" class="marker">
          <span class="dot" :style="{ background: m.color }"></span>
          <span class="t">{{ m.type }}</span>
          <span class="range">[{{ m.range[0] }}, {{ m.range[1] }}]</span>
          <span class="note">{{ m.note || '(无备注)' }}</span>
          <el-button text type="danger" size="small" @click="onDelete(m)">×</el-button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.marker-tb { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.empty { color: #9ca3af; text-align: center; padding: 12px; font-size: 13px; }
.empty.small { padding: 6px; font-size: 12px; }
.toolbar { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.toolbar .label { font-size: 12px; color: #6b7280; }
.chip {
  border: 0; padding: 4px 10px; border-radius: 12px;
  color: #fff; font-size: 12px; cursor: pointer; font-weight: 500;
}
.chip:hover { opacity: 0.85; }
.list { display: flex; flex-direction: column; gap: 4px; }
.marker {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; padding: 4px 6px;
  background: #fafbfc; border-radius: 4px;
}
.dot { width: 10px; height: 10px; border-radius: 50%; flex: none; }
.t { font-weight: 500; }
.range { color: #9ca3af; font-family: monospace; }
.note { color: #1f2937; flex: 1; }
</style>
