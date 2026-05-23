<script setup lang="ts">
/**
 * Global long-task overlay.
 *
 * Listens on the project WS for known long-task events and shows a floating
 * card stack bottom-right with title / progress / ETA / Stop button.
 *
 * Supported events:
 *   - writer.section_start / section_done / writer.report_done / writer.section_error
 *   - analysis.start / analysis.done / analysis.error
 *   - cleansing.applying / cleansing.apply_done
 *   - ingest.worker_start / ingest.worker_done
 *   - tlf.start / tlf.progress / tlf.done
 *   - ectd.start / ectd.progress / ectd.done / ectd.error
 *   - multi_review.start / multi_review.done
 *
 * Stop button posts to /api/tasks/{taskId}/cancel — if that returns 404
 * the button stays visible with a tooltip explaining cancellation isn't
 * supported for that task yet.
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { connectProjectWS, type WSEvent } from '@/api/ws'
import { cancelTask, type TaskEventDTO } from '@/api/rest'

interface TaskRow {
  id: string            // local key
  taskId?: string       // remote task id (for cancel)
  title: string
  phase: string
  progress: number      // 0..100
  startedAt: number
  status: 'running' | 'done' | 'error' | 'cancelled'
  cancellable: boolean
  total?: number
  current?: number
}

const route = useRoute()
const { t } = useI18n()

const tasks = ref<TaskRow[]>([])
let wsClose: (() => void) | null = null

const projectId = computed(() => (route.params.id as string | undefined) || '')

function upsert(id: string, patch: Partial<TaskRow>): void {
  const i = tasks.value.findIndex(t => t.id === id)
  if (i >= 0) {
    tasks.value[i] = { ...tasks.value[i], ...patch }
  } else {
    tasks.value.push({
      id, title: id, phase: '', progress: 0,
      startedAt: Date.now(), status: 'running', cancellable: true,
      ...patch,
    })
  }
}

function remove(id: string): void {
  const i = tasks.value.findIndex(t => t.id === id)
  if (i >= 0) tasks.value.splice(i, 1)
}

function autoDrop(id: string, ms = 4000): void {
  window.setTimeout(() => remove(id), ms)
}

function onEvent(ev: WSEvent): void {
  if (ev.type === 'task.event') {
    onTaskEvent((ev.payload || {}) as unknown as TaskEventDTO)
    return
  }
  const p = (ev.payload || {}) as Record<string, any>
  switch (ev.type) {
    case 'writer.section_start':
      upsert('report', {
        title: t('progress.writer.title'),
        phase: `${p.node_id || ''}`,
        progress: Math.min(95, ((p.index || 0) / Math.max(1, p.total || 1)) * 100),
        total: p.total, current: p.index, cancellable: false,
      })
      break
    case 'writer.section_done':
      upsert('report', {
        phase: `${p.node_id || ''} ✓`,
        progress: Math.min(95, ((p.index || 0) / Math.max(1, p.total || 1)) * 100),
        current: p.index,
      })
      break
    case 'report.done':
      upsert('report', { phase: t('progress.done'), progress: 100, status: 'done' })
      autoDrop('report')
      break
    case 'writer.report_done':
      upsert('report', { phase: t('progress.done'), progress: 100, status: 'done' })
      autoDrop('report')
      break
    case 'writer.section_error':
    case 'writer.report_error':
      upsert('report', {
        title: t('progress.writer.title'),
        phase: String(p.error || 'error'),
        progress: 100,
        status: 'error',
        cancellable: false,
      })
      autoDrop('report', 8000)
      break

    case 'analysis.start':
      upsert('analysis', {
        title: t('steps.analyze'),
        phase: String(p.mode || 'running'),
        progress: 25,
        cancellable: false,
      })
      break
    case 'analysis.done':
      upsert('analysis', {
        title: t('steps.analyze'),
        phase: t('progress.done'),
        progress: 100,
        status: 'done',
        cancellable: false,
      })
      autoDrop('analysis')
      break
    case 'analysis.error':
      upsert('analysis', {
        title: t('steps.analyze'),
        phase: String(p.error || 'error'),
        progress: 100,
        status: 'error',
        cancellable: false,
      })
      autoDrop('analysis', 8000)
      break

    case 'cleansing.applying':
      upsert('cleansing', {
        title: t('progress.cleansing.title'),
        phase: String(p.file_id || ''), progress: 50, cancellable: false,
      })
      break
    case 'cleansing.apply_done':
      upsert('cleansing', { phase: t('progress.done'), progress: 100, status: 'done' })
      autoDrop('cleansing')
      break

    case 'ingest.worker_start':
      upsert('ingest', {
        title: t('progress.ingest.title'),
        phase: String(p.worker || ''), progress: 30, cancellable: false,
      })
      break
    case 'ingest.worker_done':
      upsert('ingest', { phase: t('progress.done'), progress: 100, status: 'done' })
      autoDrop('ingest')
      break

    case 'tlf.start':
      upsert('tlf', {
        taskId: String(p.task_id || ''), title: t('progress.tlf.title'),
        phase: 'starting', progress: 10, cancellable: false,
      })
      break
    case 'tlf.progress':
      upsert('tlf', { phase: String(p.phase || ''), progress: Number(p.percent || 50) })
      break
    case 'tlf.done':
      upsert('tlf', { phase: t('progress.done'), progress: 100, status: 'done' })
      autoDrop('tlf')
      break

    case 'ectd.start':
      upsert('ectd', {
        taskId: String(p.task_id || ''), title: t('progress.ectd.title'),
        phase: 'starting', progress: 10, cancellable: false,
      })
      break
    case 'ectd.progress':
      upsert('ectd', { phase: String(p.phase || ''), progress: Number(p.percent || 50) })
      break
    case 'ectd.done':
      upsert('ectd', { phase: t('progress.done'), progress: 100, status: 'done' })
      autoDrop('ectd')
      break
    case 'ectd.error':
      upsert('ectd', { phase: String(p.error || 'error'), progress: 100, status: 'error' })
      autoDrop('ectd', 8000)
      break

    case 'multi_review.start':
      upsert('multi_review', {
        title: t('progress.review.title'), phase: 'starting',
        progress: 20, cancellable: false,
      })
      break
    case 'multi_review.done':
      upsert('multi_review', { phase: t('progress.done'), progress: 100, status: 'done' })
      autoDrop('multi_review')
      break
  }
}

function onTaskEvent(p: TaskEventDTO): void {
  if (!p.task_id) return
  const id = p.task_id
  const status: TaskRow['status'] = p.status === 'queued' ? 'running' : p.status
  const startedAt = p.started_at ? new Date(p.started_at).getTime() : undefined
  upsert(id, {
    taskId: p.cancellable ? p.task_id : undefined,
    title: taskEventTitle(p, id),
    phase: taskEventPhase(p),
    progress: Math.max(0, Math.min(100, Number(p.progress ?? (status === 'done' || status === 'error' ? 100 : 20)))),
    status,
    cancellable: !!p.cancellable,
    startedAt: Number.isFinite(startedAt) && startedAt ? startedAt : undefined,
  })
  if (status === 'done') autoDrop(id)
  if (status === 'error' || status === 'cancelled') autoDrop(id, 8000)
}

function taskEventTitle(p: TaskEventDTO, fallback: string): string {
  if (p.kind?.startsWith('export.')) {
    const fmt = p.kind.slice('export.'.length)
    const label = fmt === 'md_bundle' ? 'Markdown bundle' : fmt.toUpperCase()
    return t('progress.export.title', { format: label })
  }
  return p.label || p.kind || fallback
}

function taskEventPhase(p: TaskEventDTO): string {
  if (p.error) return p.error
  const phase = p.phase || p.status || ''
  const map: Record<string, string> = {
    queued: t('progress.queued'),
    running: t('progress.running'),
    start: t('progress.starting'),
    starting: t('progress.starting'),
    progress: t('progress.running'),
    done: t('progress.done'),
    error: t('progress.error'),
    cancelled: t('progress.cancelled'),
  }
  return map[phase] || phase
}

function connect(): void {
  wsClose?.()
  wsClose = null
  if (!projectId.value) return
  wsClose = connectProjectWS(projectId.value, onEvent)
}

onMounted(connect)
watch(projectId, connect)
onUnmounted(() => wsClose?.())

async function onStop(task: TaskRow): Promise<void> {
  if (!task.taskId) {
    ElMessage.info(t('progress.cancel_not_supported'))
    return
  }
  try {
    const ok = await cancelTask(task.taskId)
    if (!ok) {
      ElMessage.info(t('progress.cancel_not_supported'))
      return
    }
    upsert(task.id, { status: 'cancelled', phase: t('progress.cancelled') })
    autoDrop(task.id)
  } catch {
    ElMessage.info(t('progress.cancel_not_supported'))
  }
}

function etaText(task: TaskRow): string {
  if (task.status !== 'running' || !task.progress) return ''
  const elapsed = (Date.now() - task.startedAt) / 1000
  const total = elapsed / Math.max(0.01, task.progress / 100)
  const remaining = Math.max(0, Math.floor(total - elapsed))
  if (remaining > 90) return `${Math.floor(remaining / 60)}m ${remaining % 60}s`
  return `${remaining}s`
}
</script>

<template>
  <div v-if="tasks.length" class="overlay" aria-live="polite">
    <div v-for="task in tasks" :key="task.id" class="card" :class="task.status">
      <div class="head">
        <span class="title">{{ task.title }}</span>
        <span class="phase">{{ task.phase }}</span>
        <el-button v-if="task.status === 'running' && task.cancellable && task.taskId" link size="small"
                    :aria-label="$t('progress.stop_aria')"
                    @click="onStop(task)">×</el-button>
      </div>
      <el-progress :percentage="task.progress" :status="task.status === 'error' ? 'exception'
                                                       : task.status === 'done' ? 'success' : ''"
                    :stroke-width="6" :show-text="false" />
      <div class="meta">
        <span v-if="task.total">{{ task.current || 0 }} / {{ task.total }}</span>
        <span v-if="etaText(task)" class="eta">ETA {{ etaText(task) }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.overlay {
  position: fixed;
  right: 16px;
  bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 2400;
  max-width: 320px;
  pointer-events: none;
}
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 10px 12px;
  box-shadow: var(--shadow-md);
  pointer-events: auto;
  font-size: var(--font-size-sm);
}
.card.done   { border-color: var(--color-success); }
.card.error  { border-color: var(--color-error); }
.card.cancelled { opacity: 0.7; }
.head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.title { font-weight: 600; color: var(--color-text-strong); }
.phase {
  flex: 1;
  color: var(--color-text-mute);
  font-size: var(--font-size-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.meta {
  display: flex;
  gap: 8px;
  margin-top: 4px;
  color: var(--color-text-mute);
  font-size: var(--font-size-xs);
}
.meta .eta { margin-left: auto; }
</style>
