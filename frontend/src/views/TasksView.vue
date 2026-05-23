<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  createTask, listTasks, listUsers, patchTask, reopenTask, resolveTask,
  type ReviewTaskDTO, type UserDTO,
} from '@/api/rest'

const props = defineProps<{ id: string }>()
const router = useRouter()

const tasks = ref<ReviewTaskDTO[]>([])
const users = ref<UserDTO[]>([])
const mode = ref<'kanban' | 'list'>('kanban')
const filterAssignee = ref<string>('')
const filterSeverity = ref<string>('')
const loading = ref(false)
const newDialog = ref(false)
const newTask = ref({ assignee: 'demo_reviewer', body: '', severity: 'warn', node_id: '', due_date: '' })

async function refresh(): Promise<void> {
  loading.value = true
  try {
    const params: Record<string, string> = {}
    if (filterAssignee.value) params.assignee = filterAssignee.value
    if (filterSeverity.value) params.severity = filterSeverity.value
    tasks.value = await listTasks(props.id, params)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

async function loadUsers(): Promise<void> {
  try {
    users.value = await listUsers()
  } catch { /* ignore */ }
}

onMounted(async () => {
  await loadUsers()
  await refresh()
})

const columns = computed(() => {
  const cols: Record<string, ReviewTaskDTO[]> = {
    open: [], in_progress: [], resolved: [], wont_fix: [],
  }
  for (const t of tasks.value) {
    cols[t.status]?.push(t)
  }
  return cols
})

async function onStatus(task: ReviewTaskDTO, status: string): Promise<void> {
  try {
    await patchTask(props.id, task.id, { status }, 'demo_admin')
    await refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onReopen(task: ReviewTaskDTO): Promise<void> {
  try {
    await reopenTask(props.id, task.id)
    await refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

function gotoNode(task: ReviewTaskDTO): void {
  if (!task.node_id) {
    ElMessage.info('任务未绑定章节')
    return
  }
  router.push(`/p/${props.id}/report?node_id=${encodeURIComponent(task.node_id)}`)
}

async function submitNew(): Promise<void> {
  try {
    if (!newTask.value.body.trim() || !newTask.value.assignee) {
      ElMessage.warning('请填写 assignee + 描述')
      return
    }
    await createTask(props.id, {
      assignee: newTask.value.assignee,
      body: newTask.value.body,
      severity: newTask.value.severity,
      node_id: newTask.value.node_id || undefined,
      due_date: newTask.value.due_date || undefined,
    }, 'demo_admin')
    newDialog.value = false
    newTask.value = { assignee: 'demo_reviewer', body: '', severity: 'warn', node_id: '', due_date: '' }
    await refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

const severityType: Record<string, string> = {
  error: 'danger', warn: 'warning', info: 'info',
}
</script>

<template>
  <div class="tasks-view">
    <div class="topbar">
      <h2>任务看板</h2>
      <el-segmented v-model="mode" :options="[
        { label: 'Kanban', value: 'kanban' },
        { label: 'List', value: 'list' },
      ]" size="small" />
      <el-select v-model="filterAssignee" placeholder="全部 assignee" clearable size="small"
                  style="width: 160px" @change="refresh">
        <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
      </el-select>
      <el-select v-model="filterSeverity" placeholder="全部 severity" clearable size="small"
                  style="width: 130px" @change="refresh">
        <el-option label="error" value="error" />
        <el-option label="warn" value="warn" />
        <el-option label="info" value="info" />
      </el-select>
      <el-button type="primary" size="small" @click="newDialog = true">新建任务</el-button>
      <el-button size="small" @click="refresh">刷新</el-button>
    </div>

    <div v-if="mode === 'kanban'" class="kanban" v-loading="loading">
      <div v-for="status in ['open', 'in_progress', 'resolved', 'wont_fix']" :key="status" class="column">
        <h3>{{ status }} <span class="count">{{ columns[status].length }}</span></h3>
        <div v-for="t in columns[status]" :key="t.id" class="task-card" @click="gotoNode(t)">
          <div class="head">
            <el-tag :type="severityType[t.severity]" size="small">{{ t.severity }}</el-tag>
            <span class="assignee">@{{ t.assignee }}</span>
          </div>
          <div class="title">{{ t.title || t.body.slice(0, 60) }}</div>
          <div class="meta">
            <span v-if="t.node_id" class="chip">§ {{ t.node_id }}</span>
            <span v-if="t.due_date" class="chip due">due {{ new Date(t.due_date).toLocaleDateString() }}</span>
            <span class="chip">{{ t.source }}</span>
          </div>
          <div class="actions" @click.stop>
            <el-button v-if="status === 'open'" size="small" type="primary" link @click="onStatus(t, 'in_progress')">开始</el-button>
            <el-button v-if="status === 'in_progress'" size="small" type="success" link @click="onStatus(t, 'resolved')">完成</el-button>
            <el-button v-if="status === 'open' || status === 'in_progress'" size="small" link @click="onStatus(t, 'wont_fix')">不修</el-button>
            <el-button v-if="status === 'resolved' || status === 'wont_fix'" size="small" link @click="onReopen(t)">重开</el-button>
          </div>
        </div>
      </div>
    </div>

    <el-table v-else :data="tasks" stripe size="small" v-loading="loading" :max-height="600">
      <el-table-column prop="id" label="id" width="160" />
      <el-table-column label="severity" width="100">
        <template #default="{ row }">
          <el-tag :type="severityType[row.severity]" size="small">{{ row.severity }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="status" width="120" />
      <el-table-column prop="assignee" label="assignee" width="160" />
      <el-table-column prop="node_id" label="node" width="140" />
      <el-table-column prop="title" label="title" />
      <el-table-column prop="due_date" label="due" width="170" />
    </el-table>

    <el-dialog v-model="newDialog" title="新建任务" width="520">
      <el-form label-width="80px">
        <el-form-item label="Assignee">
          <el-select v-model="newTask.assignee">
            <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="Severity">
          <el-radio-group v-model="newTask.severity">
            <el-radio-button label="error" /><el-radio-button label="warn" /><el-radio-button label="info" />
          </el-radio-group>
        </el-form-item>
        <el-form-item label="Node ID">
          <el-input v-model="newTask.node_id" placeholder="可选, 例如 11.4" />
        </el-form-item>
        <el-form-item label="Due">
          <el-date-picker v-model="newTask.due_date" type="datetime" placeholder="可选" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newTask.body" type="textarea" :rows="4" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="newDialog = false">取消</el-button>
        <el-button type="primary" @click="submitNew">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.tasks-view { padding: 16px; }
.topbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.kanban { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
.column { background: #f3f4f6; border-radius: 6px; padding: 8px; min-height: 200px; }
.column h3 { margin: 0 0 8px; font-size: 13px; color: #374151; }
.count { color: #6b7280; font-weight: normal; }
.task-card { background: white; border: 1px solid #e5e7eb; padding: 8px; margin-bottom: 6px;
              border-radius: 4px; cursor: pointer; }
.task-card:hover { border-color: #93c5fd; }
.head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.assignee { font-size: 11px; color: #6b7280; }
.title { font-size: 13px; color: #111827; margin-bottom: 4px; }
.meta { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.chip { font-size: 10px; padding: 2px 6px; background: #eef2ff; color: #4338ca; border-radius: 3px; }
.chip.due { background: #fee2e2; color: #991b1b; }
.actions { display: flex; gap: 4px; }
</style>
