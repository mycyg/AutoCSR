<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { compareProjects, type DiffResultDTO } from '@/api/rest'
import api from '@/api/rest'

const projects = ref<Array<{ id: string; name: string }>>([])
const pidA = ref<string>('')
const pidB = ref<string>('')
const mode = ref<'outline' | 'drafts'>('outline')
const diff = ref<DiffResultDTO | null>(null)
const loading = ref(false)

async function loadProjects(): Promise<void> {
  try {
    const list = await (api as any).get('/projects')
    projects.value = list.data.map((p: any) => ({ id: p.id, name: p.name }))
  } catch (e) { /* ignore */ }
}

async function runCompare(): Promise<void> {
  if (!pidA.value || !pidB.value) {
    ElMessage.warning('请选择两个项目')
    return
  }
  loading.value = true
  try {
    diff.value = await compareProjects(pidA.value, pidB.value, mode.value)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

onMounted(loadProjects)

const kindType: Record<string, string> = {
  added: 'success', removed: 'danger', modified: 'warning', unchanged: 'info',
}
</script>

<template>
  <div class="compare-view">
    <div class="topbar">
      <h2>跨项目对比</h2>
      <el-select v-model="pidA" placeholder="项目 A" filterable style="width: 240px">
        <el-option v-for="p in projects" :key="p.id" :label="`${p.name} (${p.id})`" :value="p.id" />
      </el-select>
      <span>↔</span>
      <el-select v-model="pidB" placeholder="项目 B" filterable style="width: 240px">
        <el-option v-for="p in projects" :key="p.id" :label="`${p.name} (${p.id})`" :value="p.id" />
      </el-select>
      <el-radio-group v-model="mode">
        <el-radio-button label="outline" />
        <el-radio-button label="drafts" />
      </el-radio-group>
      <el-button type="primary" :loading="loading" @click="runCompare">对比</el-button>
    </div>

    <div v-if="diff" class="summary">
      <el-tag v-for="[k, v] in Object.entries(diff.summary)" :key="k" type="info" class="chip">
        {{ k }}: {{ v }}
      </el-tag>
    </div>

    <el-table v-if="diff && mode === 'outline'" :data="diff.outline" stripe size="small" :max-height="600">
      <el-table-column prop="node_id" label="node_id" width="140" />
      <el-table-column prop="title" label="title" />
      <el-table-column label="kind" width="120">
        <template #default="{ row }">
          <el-tag :type="kindType[row.kind]" size="small">{{ row.kind }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="notes" label="notes" />
    </el-table>

    <div v-if="diff && mode === 'drafts'" class="drafts-diff">
      <div v-for="d in diff.drafts" :key="d.node_id" class="diff-block">
        <h4>{{ d.node_id }} — {{ d.title }} <small>(+{{ d.n_added }} / -{{ d.n_removed }})</small></h4>
        <pre>{{ d.diff }}</pre>
      </div>
      <div v-if="diff.drafts.length === 0" class="empty">两个项目的草稿完全一致。</div>
    </div>
  </div>
</template>

<style scoped>
.compare-view { padding: 16px; }
.topbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.summary { margin-bottom: 12px; display: flex; gap: 6px; flex-wrap: wrap; }
.diff-block { background: #f9fafb; padding: 10px; margin-bottom: 8px; border-left: 3px solid #6366f1; }
.diff-block pre { font-family: ui-monospace, monospace; font-size: 11px; white-space: pre-wrap; margin: 0; }
.empty { color: #6b7280; padding: 16px; text-align: center; }
</style>
