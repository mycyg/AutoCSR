<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getDraftDiff, getDraftVersions,
  type DiffResultDTO,
} from '@/api/rest'

const props = defineProps<{
  projectId: string
  nodeId: string | null
}>()

const versions = ref<number[]>([])
const v1 = ref<number | null>(null)
const v2 = ref<number | null>(null)
const diff = ref<DiffResultDTO | null>(null)
const loading = ref(false)

async function loadVersions(): Promise<void> {
  if (!props.nodeId) {
    versions.value = []
    v1.value = v2.value = null
    diff.value = null
    return
  }
  try {
    versions.value = await getDraftVersions(props.projectId, props.nodeId)
    if (versions.value.length >= 2) {
      v1.value = versions.value[versions.value.length - 2]
      v2.value = versions.value[versions.value.length - 1]
      await loadDiff()
    } else if (versions.value.length === 1) {
      v1.value = versions.value[0]
      v2.value = versions.value[0]
      await loadDiff()
    }
  } catch (e) {
    versions.value = []
  }
}

async function loadDiff(): Promise<void> {
  if (!props.nodeId) return
  if (v1.value === null || v2.value === null) return
  loading.value = true
  try {
    diff.value = await getDraftDiff(props.projectId, props.nodeId, v1.value, v2.value)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

watch(() => props.nodeId, () => { void loadVersions() }, { immediate: true })

const summary = computed(() => diff.value?.summary || {})
</script>

<template>
  <div class="diff-view">
    <div v-if="!nodeId" class="empty">请先选择章节</div>
    <template v-else>
      <div class="bar">
        <el-select v-model="v1" placeholder="v1" size="small" style="width: 90px"
                    @change="loadDiff">
          <el-option v-for="v in versions" :key="v" :label="`v${v}`" :value="v" />
        </el-select>
        <span class="arrow">→</span>
        <el-select v-model="v2" placeholder="v2" size="small" style="width: 90px"
                    @change="loadDiff">
          <el-option v-for="v in versions" :key="v" :label="`v${v}`" :value="v" />
        </el-select>
        <span class="summary">
          <el-tag v-if="summary.insert" type="success" size="small">+{{ summary.insert }}</el-tag>
          <el-tag v-if="summary.delete" type="danger" size="small">-{{ summary.delete }}</el-tag>
          <el-tag v-if="summary.replace" type="warning" size="small">~{{ summary.replace }}</el-tag>
        </span>
        <el-button size="small" @click="loadVersions">刷新</el-button>
      </div>

      <div v-if="loading" class="empty">加载中…</div>
      <div v-else-if="!diff" class="empty">至少需要两个版本才能对比</div>
      <div v-else class="panes">
        <div class="pane">
          <div class="head">v{{ diff.v1 }}</div>
          <div class="body">
            <span v-for="(b, i) in diff.blocks" :key="i"
                  :class="['block', b.op]">{{ b.v1_text }}</span>
          </div>
        </div>
        <div class="pane">
          <div class="head">v{{ diff.v2 }}</div>
          <div class="body">
            <span v-for="(b, i) in diff.blocks" :key="i"
                  :class="['block', b.op]">{{ b.v2_text }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.diff-view { padding: 12px; display: flex; flex-direction: column; gap: 8px; height: 100%; }
.empty { color: #9ca3af; text-align: center; padding: 24px; font-size: 13px; }
.bar { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.arrow { color: #6b7280; }
.summary { margin-left: 6px; display: flex; gap: 4px; }
.panes { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; flex: 1; overflow: auto; }
.pane { display: flex; flex-direction: column; min-width: 0; }
.pane .head { padding: 4px 8px; background: #f3f4f6; font-size: 12px; font-weight: 600; }
.pane .body {
  flex: 1; padding: 8px;
  background: #fafbfc; border: 1px solid #e5e7eb; border-radius: 4px;
  font-family: 'Fira Code', monospace; font-size: 12px; line-height: 1.55;
  white-space: pre-wrap; word-break: break-word; overflow: auto;
}
.block.equal { color: #1f2937; }
.block.insert { background: #dcfce7; color: #166534; }
.block.delete { background: #fee2e2; color: #991b1b; text-decoration: line-through; }
.block.replace { background: #fef3c7; color: #92400e; }
</style>
