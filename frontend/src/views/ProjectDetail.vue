<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import ProjectMembersDialog from '@/components/global/ProjectMembersDialog.vue'
import EmptyState from '@/components/global/EmptyState.vue'
import { getWorkbench, listProjectMembers, type WorkbenchDTO } from '@/api/rest'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'
import { useResponsive } from '@/composables/useResponsive'

const props = defineProps<{ id: string }>()
const router = useRouter()
const auth = useAuthStore()
const { t } = useI18n()
const { isMobile } = useResponsive()

const loading = ref(false)
const error = ref<string | null>(null)
const wb = ref<WorkbenchDTO | null>(null)
const membersOpen = ref(false)
const canManageMembers = ref(false)

const steps = [
  { key: 'intake', path: 'intake' },
  { key: 'cleanse', path: 'cleanse' },
  { key: 'analyze', path: 'analyze' },
  { key: 'outline', path: 'outline' },
  { key: 'report', path: 'report' },
  { key: 'review', path: 'review' },
  { key: 'tasks', path: 'tasks' },
  { key: 'export', path: 'export' },
]

const currentIndex = computed(() => {
  const idx = steps.findIndex(s => s.key === wb.value?.current_step)
  return idx < 0 ? 0 : idx
})

const riskTotal = computed(() => {
  const r = wb.value?.risks
  return r ? r.error + r.warn + r.info + r.hallucination : 0
})

const nextActionLabel = computed(() => {
  const step = wb.value?.next_action?.step
  return step ? t('workbench.continue_step', { step: stepLabel(step) }) : t('common.open')
})

function stepLabel(key: string): string {
  return t(`steps.${key}`)
}

function stepMeta(key: string): string {
  const summary = wb.value?.steps[key]
  const done = summary?.done || 0
  const error = summary?.error || 0
  return error
    ? t('workbench.step_meta_error', { done, error })
    : t('workbench.step_meta_done', { done })
}

function statusLabel(status?: string): string {
  const key = status || 'open'
  return t(`tasks.status_${key}`, key)
}

async function refresh(): Promise<void> {
  loading.value = true
  error.value = null
  try {
    wb.value = await getWorkbench(props.id)
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

async function refreshMemberCap(): Promise<void> {
  canManageMembers.value = false
  if (!auth.isAuthenticated && !auth.user) return
  try {
    const members = await listProjectMembers(props.id)
    const me = auth.user?.id
    canManageMembers.value = !!members.find(m => m.user_id === me && m.role === 'owner') || auth.isAdmin
  } catch {
    canManageMembers.value = false
  }
}

function go(path: string): void {
  router.push(path.startsWith('/p/') ? path : `/p/${props.id}/${path}`)
}

function openTask(href: string): void {
  router.push(href || `/p/${props.id}/tasks`)
}

function fmtTime(ts?: string | null): string {
  if (!ts) return ''
  try { return new Date(ts).toLocaleString() } catch { return String(ts) }
}

function stepState(key: string): 'done' | 'current' | 'blocked' {
  const idx = steps.findIndex(s => s.key === key)
  if (idx < currentIndex.value) return 'done'
  if (idx === currentIndex.value) return 'current'
  return 'blocked'
}

async function onRefresh(): Promise<void> {
  await refresh()
  ElMessage.success(t('common.refresh'))
}

onMounted(async () => {
  await refresh()
  void refreshMemberCap()
})

watch(() => props.id, async () => {
  await refresh()
  void refreshMemberCap()
})
</script>

<template>
  <div class="workbench" :class="{ 'workbench--mobile': isMobile }" v-loading="loading">
    <EmptyState v-if="error && !wb"
                 icon="!"
                 :title="$t('errors.unknown')"
                 :description="error"
                 :cta-text="$t('common.refresh')"
                 @cta="refresh" />

    <template v-else-if="wb">
      <section class="hero-band" aria-labelledby="project-title">
        <div class="hero-copy">
          <div class="eyebrow">{{ wb.project.principle_id || 'ICH E3' }} · {{ wb.project.language || 'zh' }}</div>
          <h1 id="project-title">{{ wb.project.name }}</h1>
          <p>{{ $t('workbench.subtitle') }}</p>
          <div class="hero-actions">
            <el-button type="primary" size="large" @click="go(wb.next_action.href)">
              {{ nextActionLabel }}
            </el-button>
            <el-button size="large" plain @click="go('report')">{{ $t('steps.report') }}</el-button>
            <el-button size="large" text @click="onRefresh">{{ $t('common.refresh') }}</el-button>
            <el-button v-if="canManageMembers" size="large" text @click="membersOpen = true">
              {{ t('members.title') }}
            </el-button>
          </div>
        </div>
        <div class="signal-grid" aria-label="Project metrics">
          <div class="signal">
            <span>{{ wb.metrics.files }}</span>
            <small>{{ $t('workbench.metrics.files') }}</small>
          </div>
          <div class="signal">
            <span>{{ wb.metrics.stats }}</span>
            <small>{{ $t('workbench.metrics.stats') }}</small>
          </div>
          <div class="signal">
            <span>{{ wb.metrics.drafts }}</span>
            <small>{{ $t('workbench.metrics.drafts') }}</small>
          </div>
          <div class="signal" :class="{ risk: riskTotal > 0 }">
            <span>{{ riskTotal }}</span>
            <small>{{ $t('workbench.metrics.risks') }}</small>
          </div>
        </div>
      </section>

      <section class="workflow-band" aria-labelledby="workflow-title">
        <div class="section-head">
          <div>
            <h2 id="workflow-title">{{ $t('workbench.workflow') }}</h2>
            <p>{{ $t('workbench.workflow_hint') }}</p>
          </div>
          <el-tag type="primary" effect="plain">{{ stepLabel(wb.current_step) }}</el-tag>
        </div>
        <div class="steps" role="list">
          <button v-for="(s, i) in steps"
                  :key="s.key"
                  type="button"
                  class="step"
                  :class="stepState(s.key)"
                  role="listitem"
                  @click="go(s.path)">
            <span class="num">{{ i + 1 }}</span>
            <span class="label">{{ stepLabel(s.key) }}</span>
            <span class="meta">
              {{ stepMeta(s.key) }}
            </span>
          </button>
        </div>
      </section>

      <section class="grid-band">
        <article class="panel tasks-panel">
          <div class="section-head compact">
            <div>
              <h2>{{ $t('workbench.open_tasks') }}</h2>
              <p>{{ wb.metrics.open_tasks }} {{ $t('tasks.title') }}</p>
            </div>
            <el-button text @click="go('tasks')">{{ $t('common.open') }}</el-button>
          </div>
          <div v-if="wb.tasks.length" class="task-list">
            <button v-for="task in wb.tasks"
                    :key="task.id"
                    type="button"
                    class="task-row"
                    @click="openTask(task.href)">
              <span class="severity" :class="task.severity"></span>
              <span class="task-main">
                <strong>{{ task.title }}</strong>
                <small>{{ statusLabel(task.status) }} · @{{ task.assignee }}<template v-if="task.node_id"> · {{ task.node_id }}</template></small>
              </span>
            </button>
          </div>
          <p v-else class="empty-line">{{ $t('tasks.empty_title') }}</p>
        </article>

        <article class="panel risk-panel">
          <div class="section-head compact">
            <div>
              <h2>{{ $t('workbench.risk_review') }}</h2>
              <p>{{ $t('workbench.risk_hint') }}</p>
            </div>
            <el-button text @click="go('review')">{{ $t('steps.review') }}</el-button>
          </div>
          <div class="risk-stack">
            <div class="risk-line error"><span>{{ $t('workbench.risk_error') }}</span><b>{{ wb.risks.error }}</b></div>
            <div class="risk-line warn"><span>{{ $t('workbench.risk_warn') }}</span><b>{{ wb.risks.warn }}</b></div>
            <div class="risk-line info"><span>{{ $t('workbench.risk_info') }}</span><b>{{ wb.risks.info }}</b></div>
            <div class="risk-line hallucination"><span>{{ $t('workbench.risk_hallucination') }}</span><b>{{ wb.risks.hallucination }}</b></div>
          </div>
        </article>

        <article class="panel activity-panel">
          <div class="section-head compact">
            <div>
              <h2>{{ $t('workbench.activity') }}</h2>
              <p>{{ $t('workbench.activity_hint') }}</p>
            </div>
          </div>
          <ol v-if="wb.activity.length" class="activity">
            <li v-for="a in wb.activity" :key="a.kind + a.label + a.ts">
              <button type="button" @click="go(a.href)">
                <span>{{ a.kind }}</span>
                <strong>{{ a.label }}</strong>
                <small>{{ fmtTime(a.ts) }}</small>
              </button>
            </li>
          </ol>
          <p v-else class="empty-line">{{ $t('common.empty') }}</p>
        </article>

        <article class="panel export-panel">
          <div class="section-head compact">
            <div>
              <h2>{{ $t('export.history') }}</h2>
              <p>{{ $t('workbench.export_count', { n: wb.metrics.exports }) }}</p>
            </div>
            <el-button text @click="go('export')">{{ $t('steps.export') }}</el-button>
          </div>
          <div v-if="wb.exports.length" class="exports">
            <button v-for="e in wb.exports"
                    :key="e.filename"
                    type="button"
                    @click="go('export')">
              <strong>{{ e.filename }}</strong>
              <small>{{ fmtTime(e.created_at) }}</small>
            </button>
          </div>
          <p v-else class="empty-line">{{ $t('export.no_history') }}</p>
        </article>
      </section>
    </template>

    <ProjectMembersDialog v-model="membersOpen" :project-id="props.id" />
  </div>
</template>

<style scoped>
.workbench {
  min-height: calc(100vh - 56px);
  background:
    linear-gradient(140deg, rgba(8, 145, 178, 0.08), rgba(37, 99, 235, 0.08) 38%, transparent 58%),
    var(--color-bg);
  overflow: auto;
  padding: 24px;
}
.hero-band,
.workflow-band,
.grid-band {
  max-width: 1240px;
  margin: 0 auto 18px;
}
.hero-band {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 420px;
  gap: 18px;
  align-items: stretch;
  padding: 28px;
  border: 1px solid rgba(8, 145, 178, 0.18);
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--color-surface) 88%, var(--color-primary-soft));
  box-shadow: var(--shadow-md);
}
.eyebrow {
  color: var(--color-primary);
  font-weight: 700;
  letter-spacing: 0;
  font-size: var(--font-size-sm);
  text-transform: uppercase;
}
.hero-copy h1 {
  margin: 8px 0;
  color: var(--color-text-strong);
  font-size: 28px;
  line-height: 1.2;
}
.hero-copy p {
  max-width: 720px;
  color: var(--color-text-mute);
  margin: 0 0 20px;
  font-size: var(--font-size-xl);
}
.hero-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.signal-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.signal {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  border-radius: var(--radius-md);
  padding: 18px;
  min-height: 96px;
}
.signal span {
  display: block;
  color: var(--color-text-strong);
  font-size: 30px;
  font-weight: 760;
  line-height: 1;
}
.signal small {
  color: var(--color-text-mute);
  font-size: var(--font-size-sm);
}
.signal.risk {
  border-color: color-mix(in srgb, var(--color-warn), var(--color-border) 50%);
}
.workflow-band,
.panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}
.workflow-band { padding: 18px; }
.section-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.section-head.compact { margin-bottom: 10px; }
.section-head h2 {
  margin: 0;
  color: var(--color-text-strong);
  font-size: var(--font-size-2xl);
}
.section-head p {
  margin: 4px 0 0;
  color: var(--color-text-mute);
  font-size: var(--font-size-sm);
}
.steps {
  display: grid;
  grid-template-columns: repeat(8, minmax(112px, 1fr));
  gap: 8px;
}
.step {
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  border-radius: var(--radius-md);
  min-height: 96px;
  padding: 10px;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.step:hover,
.step:focus-visible {
  border-color: var(--color-primary);
  background: var(--color-primary-soft);
}
.step.done .num { background: var(--color-success); }
.step.current {
  border-color: var(--color-primary);
  box-shadow: inset 0 0 0 1px var(--color-primary);
}
.step.blocked { opacity: 0.72; }
.num {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  display: inline-grid;
  place-items: center;
  background: var(--color-primary);
  color: #fff;
  font-size: var(--font-size-xs);
  font-weight: 700;
}
.label { font-weight: 700; color: var(--color-text-strong); }
.meta { color: var(--color-text-mute); font-size: var(--font-size-xs); }
.grid-band {
  display: grid;
  grid-template-columns: 1.1fr 0.9fr;
  gap: 18px;
}
.panel {
  padding: 18px;
  min-height: 240px;
}
.task-list,
.exports {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.task-row,
.exports button,
.activity button {
  width: 100%;
  border: 1px solid var(--color-border);
  background: var(--color-surface-2);
  color: var(--color-text);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  text-align: left;
  cursor: pointer;
}
.task-row {
  display: grid;
  grid-template-columns: 8px 1fr;
  gap: 10px;
  align-items: center;
}
.task-row:hover,
.exports button:hover,
.activity button:hover {
  border-color: var(--color-primary);
}
.severity {
  width: 8px;
  align-self: stretch;
  border-radius: 99px;
  background: var(--color-info);
}
.severity.error { background: var(--color-error); }
.severity.warn { background: var(--color-warn); }
.severity.info { background: var(--color-primary); }
.task-main { min-width: 0; display: grid; gap: 2px; }
.task-main strong,
.exports strong,
.activity strong {
  color: var(--color-text-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.task-main small,
.exports small,
.activity small {
  color: var(--color-text-mute);
  font-size: var(--font-size-xs);
}
.risk-stack {
  display: grid;
  gap: 8px;
}
.risk-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  border-radius: var(--radius-md);
  background: var(--color-surface-2);
  border-left: 3px solid var(--color-info);
}
.risk-line.error { border-left-color: var(--color-error); }
.risk-line.warn { border-left-color: var(--color-warn); }
.risk-line.hallucination { border-left-color: var(--color-primary); }
.risk-line b { color: var(--color-text-strong); font-size: var(--font-size-2xl); }
.activity {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 8px;
}
.activity button {
  display: grid;
  gap: 2px;
}
.activity span {
  color: var(--color-primary);
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  font-weight: 700;
}
.empty-line {
  color: var(--color-text-mute);
  margin: 14px 0 0;
}
@media (max-width: 1180px) {
  .hero-band { grid-template-columns: 1fr; }
  .steps { grid-template-columns: repeat(4, minmax(0, 1fr)); }
}
@media (max-width: 767px) {
  .workbench {
    min-height: calc(100dvh - 48px);
    padding: 12px;
  }
  .hero-band {
    padding: 18px;
  }
  .hero-copy h1 { font-size: 22px; }
  .hero-copy p { font-size: var(--font-size-lg); }
  .signal-grid,
  .grid-band {
    grid-template-columns: 1fr;
  }
  .steps {
    grid-template-columns: 1fr;
  }
  .step {
    min-height: 64px;
    display: grid;
    grid-template-columns: 28px 1fr;
    align-items: center;
  }
  .step .meta {
    grid-column: 2;
  }
}
</style>
