<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'
import {
  getMultiReview, getReview, getReviewHistory, listUsers,
  patchReviewIssue, runMultiReview, startReview, taskFromIssue,
  type MultiReviewDTO, type ReviewIssueDTO, type ReviewResultDTO,
  type ReviewHistoryDTO, type UserDTO,
} from '@/api/rest'
import HallucinationPanel from '@/components/global/HallucinationPanel.vue'
import { handleApiError } from '@/utils/errors'
import { reportDeepLink } from '@/utils/deepLink'

const props = defineProps<{ id: string }>()
const router = useRouter()

const review = ref<ReviewResultDTO | null>(null)
const history = ref<ReviewHistoryDTO[]>([])
const running = ref(false)
const currentHistIdx = ref<number>(-1)   // -1 = latest
const mode = ref<'classic' | 'multi' | 'hallucination'>('classic')
const multi = ref<MultiReviewDTO | null>(null)
const users = ref<UserDTO[]>([])
const taskDlg = ref({ visible: false, issueId: '', assignee: 'demo_reviewer' })

async function refresh(): Promise<void> {
  try {
    review.value = await getReview(props.id)
    history.value = await getReviewHistory(props.id)
    multi.value = await getMultiReview(props.id)
  } catch (e) {
    review.value = null
  }
}

async function loadUsers(): Promise<void> {
  try { users.value = await listUsers() } catch { /* ignore */ }
}

onMounted(async () => {
  await loadUsers()
  await refresh()
})

async function onStartMulti(): Promise<void> {
  running.value = true
  try {
    multi.value = await runMultiReview(props.id)
    ElMessage.success(`三审完成: ${JSON.stringify(multi.value.combined_count)}`)
  } catch (e) {
    handleApiError(e)
  } finally {
    running.value = false
  }
}

function openTaskDlg(issueId: string): void {
  taskDlg.value = { visible: true, issueId, assignee: 'demo_reviewer' }
}

async function submitTask(): Promise<void> {
  try {
    await taskFromIssue(props.id, taskDlg.value.issueId, {
      assignee: taskDlg.value.assignee,
    })
    taskDlg.value.visible = false
    ElMessage.success('已转换为任务')
  } catch (e) {
    handleApiError(e)
  }
}

async function onStart(): Promise<void> {
  running.value = true
  try {
    review.value = await startReview(props.id)
    history.value = await getReviewHistory(props.id)
    ElMessage.success(`审查完成：${review.value?.passed ? '通过' : '有未处理 issue'}`)
  } catch (e) {
    handleApiError(e)
  } finally {
    running.value = false
  }
}

async function onIgnore(issue: ReviewIssueDTO, ignored: boolean): Promise<void> {
  try {
    review.value = await patchReviewIssue(props.id, issue.id, ignored)
  } catch (e) {
    handleApiError(e)
  }
}

function gotoSection(issue: ReviewIssueDTO): void {
  const nodeId = issue.location?.node_id
  if (!nodeId) {
    ElMessage.info('此 issue 未绑定具体章节')
    return
  }
  const range = issue.location?.char_range
  const highlight = Array.isArray(range) && range.length === 2
    ? `range:${range[0]}-${range[1]}`
    : `issue:${issue.id}`
  router.push(reportDeepLink(props.id, nodeId, { panel: 'comments', highlight }))
}

const grouped = computed(() => {
  const out: Record<string, ReviewIssueDTO[]> = { error: [], warn: [], info: [] }
  for (const i of (review.value?.issues || [])) {
    if (i.ignored) continue
    out[i.severity]?.push(i)
  }
  return out
})

const ignoredIssues = computed(() =>
  (review.value?.issues || []).filter(i => i.ignored),
)

const counts = computed(() => ({
  error: grouped.value.error.length,
  warn: grouped.value.warn.length,
  info: grouped.value.info.length,
}))
</script>

<template>
  <div class="review-view">
    <div class="topbar">
      <el-radio-group v-model="mode" size="small">
        <el-radio-button label="classic">单审 (M10)</el-radio-button>
        <el-radio-button label="multi">三审 (M16)</el-radio-button>
        <el-radio-button label="hallucination">{{ $t('review.tab_hallucination') }}</el-radio-button>
      </el-radio-group>
      <el-button v-if="mode === 'classic'" type="primary" :loading="running" @click="onStart">
        触发审查
      </el-button>
      <el-button v-else-if="mode === 'multi'" type="primary" :loading="running" @click="onStartMulti">
        触发三审
      </el-button>
      <span v-if="review?.created_at" class="ts">
        最近审查 {{ new Date(review.created_at).toLocaleString('zh-CN') }}
      </span>
      <span class="status">
        <el-tag :type="review?.passed ? 'success' : 'danger'" size="small">
          {{ review?.passed ? 'PASSED' : 'FAILED' }}
        </el-tag>
      </span>
      <span class="counts">
        <el-tag type="danger" size="small">error {{ counts.error }}</el-tag>
        <el-tag type="warning" size="small">warn {{ counts.warn }}</el-tag>
        <el-tag type="info" size="small">info {{ counts.info }}</el-tag>
      </span>
      <span class="checkers">
        <span v-for="c in (review?.checkers || [])" :key="c.name" class="chk">
          <span class="dot" :class="{ ok: c.ok, fail: !c.ok }"></span>
          {{ c.name }} ({{ c.issues_count }})
        </span>
      </span>
    </div>

    <div v-if="mode === 'multi' && multi" class="multi-summary">
      <el-tabs>
        <el-tab-pane :label="`Statistician (${(multi.statistician?.issues?.length || 0)})`">
          <div v-for="iss in (multi.statistician?.issues || [])" :key="iss.id" class="issue">
            <div class="head">
              <el-tag size="small" :type="iss.severity === 'error' ? 'danger' : iss.severity === 'warn' ? 'warning' : 'info'">
                {{ iss.severity }}
              </el-tag>
              <span class="loc" v-if="iss.location?.node_id">→ {{ iss.location.node_id }}</span>
            </div>
            <div class="msg">{{ iss.message }}</div>
            <div v-if="iss.suggestion" class="sug">建议：{{ iss.suggestion }}</div>
            <div class="ops">
              <el-button v-if="iss.location?.node_id" size="small" plain @click="gotoSection(iss)">跳转章节</el-button>
              <el-button size="small" type="primary" plain @click="openTaskDlg(iss.id)">转任务</el-button>
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane :label="`Medical (${(multi.medical?.issues?.length || 0)})`">
          <div v-for="iss in (multi.medical?.issues || [])" :key="iss.id" class="issue">
            <div class="head">
              <el-tag size="small" :type="iss.severity === 'error' ? 'danger' : iss.severity === 'warn' ? 'warning' : 'info'">
                {{ iss.severity }}
              </el-tag>
              <span class="loc" v-if="iss.location?.node_id">→ {{ iss.location.node_id }}</span>
            </div>
            <div class="msg">{{ iss.message }}</div>
            <div v-if="iss.suggestion" class="sug">建议：{{ iss.suggestion }}</div>
            <div class="ops">
              <el-button v-if="iss.location?.node_id" size="small" plain @click="gotoSection(iss)">跳转章节</el-button>
              <el-button size="small" type="primary" plain @click="openTaskDlg(iss.id)">转任务</el-button>
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane :label="`Regulatory (${(multi.regulatory?.issues?.length || 0)})`">
          <div v-for="iss in (multi.regulatory?.issues || [])" :key="iss.id" class="issue">
            <div class="head">
              <el-tag size="small" :type="iss.severity === 'error' ? 'danger' : iss.severity === 'warn' ? 'warning' : 'info'">
                {{ iss.severity }}
              </el-tag>
              <span class="loc" v-if="iss.location?.node_id">→ {{ iss.location.node_id }}</span>
            </div>
            <div class="msg">{{ iss.message }}</div>
            <div v-if="iss.suggestion" class="sug">建议：{{ iss.suggestion }}</div>
            <div class="ops">
              <el-button v-if="iss.location?.node_id" size="small" plain @click="gotoSection(iss)">跳转章节</el-button>
              <el-button size="small" type="primary" plain @click="openTaskDlg(iss.id)">转任务</el-button>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>

    <div v-if="mode === 'hallucination'" class="hallucination-wrap">
      <HallucinationPanel :project-id="props.id" />
    </div>

    <div v-show="mode === 'classic'" class="body">
      <div class="main">
        <el-collapse :default-active="['error', 'warn']">
          <el-collapse-item v-for="sev in ['error', 'warn', 'info']" :key="sev"
                              :name="sev">
            <template #title>
              <span class="sev-title" :class="sev">
                {{ sev.toUpperCase() }} ({{ grouped[sev].length }})
              </span>
            </template>
            <div v-if="!grouped[sev].length" class="empty">（无）</div>
            <div v-for="iss in grouped[sev]" :key="iss.id" class="issue">
              <div class="head">
                <el-tag size="small" :type="sev === 'error' ? 'danger' : sev === 'warn' ? 'warning' : 'info'">
                  {{ iss.checker }}
                </el-tag>
                <span class="loc" v-if="iss.location?.node_id">→ 节 {{ iss.location.node_id }}</span>
              </div>
              <div class="msg">{{ iss.message }}</div>
              <div v-if="iss.suggestion" class="sug">建议：{{ iss.suggestion }}</div>
              <div class="ops">
                <el-button size="small" plain @click="gotoSection(iss)">跳转章节</el-button>
                <el-button size="small" type="primary" plain @click="openTaskDlg(iss.id)">转任务</el-button>
                <el-button size="small" type="info" @click="onIgnore(iss, true)">忽略</el-button>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>

        <div v-if="ignoredIssues.length" class="ignored">
          <h4>已忽略 ({{ ignoredIssues.length }})</h4>
          <div v-for="iss in ignoredIssues" :key="iss.id" class="issue muted">
            <div class="head">
              <el-tag size="small">{{ iss.checker }}</el-tag>
              <span class="loc" v-if="iss.location?.node_id">→ {{ iss.location.node_id }}</span>
            </div>
            <div class="msg">{{ iss.message }}</div>
            <el-button size="small" plain @click="onIgnore(iss, false)">取消忽略</el-button>
          </div>
        </div>
      </div>

      <div class="side">
        <h4>审查历史</h4>
        <div v-if="!history.length" class="empty">尚无审查记录</div>
        <div v-for="(h, i) in history" :key="i" class="hist"
             :class="{ active: i === currentHistIdx }">
          <div class="ts">{{ new Date(h.created_at).toLocaleString('zh-CN') }}</div>
          <div class="badges">
            <el-tag :type="h.passed ? 'success' : 'danger'" size="small">
              {{ h.passed ? 'PASSED' : 'FAILED' }}
            </el-tag>
            <span class="cnt">{{ h.n_errors }}/{{ h.n_warns }}/{{ h.n_infos }}</span>
          </div>
        </div>
      </div>
    </div>

    <el-dialog v-model="taskDlg.visible" title="转换为任务" width="420">
      <el-form label-width="80px">
        <el-form-item label="Assignee">
          <el-select v-model="taskDlg.assignee">
            <el-option v-for="u in users" :key="u.id" :label="u.name" :value="u.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="taskDlg.visible = false">取消</el-button>
        <el-button type="primary" @click="submitTask">创建任务</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.review-view { height: calc(100vh - 56px); display: flex; flex-direction: column; background: var(--color-bg); }
.hallucination-wrap { flex: 1; overflow: auto; padding: 16px; }
.topbar { display: flex; align-items: center; gap: 10px; padding: 10px 16px;
  background: var(--color-surface); border-bottom: 1px solid var(--color-border); flex-wrap: wrap; }
.topbar .ts { color: var(--color-text-mute); font-size: 12px; }
.topbar .counts { display: flex; gap: 4px; }
.topbar .checkers { display: flex; gap: 10px; margin-left: auto; }
.chk { font-size: 12px; color: var(--color-text-mute); display: inline-flex; gap: 4px; align-items: center; }
.chk .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-text-faint); }
.chk .dot.ok { background: #67c23a; }
.chk .dot.fail { background: #f56c6c; }
.body { flex: 1; display: grid; grid-template-columns: 1fr 280px; gap: 0; overflow: hidden; }
.main { padding: 12px 16px; overflow: auto; }
.side { padding: 12px; background: var(--color-surface); border-left: 1px solid var(--color-border); overflow: auto; }
.side h4 { margin: 0 0 8px 0; color: var(--color-text-strong); font-size: 13px; }
.empty { color: var(--color-text-faint); padding: 8px; font-size: 12px; }
.sev-title.error { color: #f56c6c; font-weight: 600; }
.sev-title.warn { color: #e6a23c; font-weight: 600; }
.sev-title.info { color: #909399; font-weight: 600; }
.issue { padding: 10px 12px; background: var(--color-surface-2); border-radius: 6px;
  border: 1px solid var(--color-border); margin-bottom: 8px; }
.issue.muted { opacity: 0.55; }
.issue .head { display: flex; gap: 8px; align-items: center; margin-bottom: 4px; }
.issue .loc { color: var(--color-text-mute); font-size: 12px; }
.issue .msg { font-size: 13px; color: var(--color-text-strong); line-height: 1.5; }
.issue .sug { font-size: 12px; color: var(--color-text-mute); margin-top: 4px; }
.issue .ops { margin-top: 6px; display: flex; gap: 6px; }
.hist { padding: 6px 8px; border-radius: 4px; margin-bottom: 4px; }
.hist:hover { background: var(--color-surface-3); }
.hist.active { background: var(--color-primary-soft); }
.hist .ts { font-size: 11px; color: var(--color-text-mute); }
.hist .badges { display: flex; gap: 4px; margin-top: 2px; align-items: center; }
.hist .cnt { font-family: monospace; color: var(--color-text-mute); font-size: 11px; }
@media (max-width: 767px) {
  .review-view { height: calc(100dvh - 48px); }
  .topbar { padding: 8px 10px; align-items: stretch; }
  .topbar :deep(.el-radio-group) { width: 100%; overflow-x: auto; flex-wrap: nowrap; }
  .topbar .checkers { width: 100%; margin-left: 0; overflow-x: auto; padding-bottom: 2px; }
  .body { grid-template-columns: 1fr; overflow: auto; }
  .main { overflow: visible; padding: 10px; }
  .side { border-left: 0; border-top: 1px solid var(--color-border); max-height: 240px; }
  .issue .ops { flex-wrap: wrap; }
}
</style>
