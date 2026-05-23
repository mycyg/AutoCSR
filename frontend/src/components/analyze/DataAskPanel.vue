<script setup lang="ts">
/**
 * Data Q&A chat — bottom of the AnalyzeView.
 *
 * The user types a natural-language question, the analyst agent generates
 * sandbox Python, we stream the LLM thinking → code → table → chart via
 * WS events, and finally drop a "已保存为 StatBlock" link.
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import { askData, getAskHistory, type AskHistoryEntryDTO, type AskResponseDTO } from '@/api/rest'
import { connectProjectWS } from '@/api/ws'
import CodeRunCard from '@/components/sandbox/CodeRunCard.vue'
import EChartsRenderer from '@/components/sandbox/EChartsRenderer.vue'
import { sanitizeMarkdownHtml } from '@/utils/sanitize'

const props = defineProps<{ projectId: string }>()
const emit = defineEmits<{ (e: 'stat-block-saved'): void }>()

interface AskMessage {
  id: string
  query: string
  plan: string
  code: string
  status: 'pending' | 'code_ready' | 'sandbox_running' | 'done' | 'error'
  runId: string | null
  statBlock: AskResponseDTO['stat_block'] | null
  stdout: string
  stderr: string
  artifacts: string[]
  chartJson: Record<string, unknown> | null
  pngUrl: string | null
  errorMsg: string
}

const input = ref('')
const sending = ref(false)
const messages = reactive<AskMessage[]>([])
const history = ref<AskHistoryEntryDTO[]>([])
let wsClose: (() => void) | null = null

const placeholder = computed(() =>
  '例如：TRT A vs Placebo 在 BMI>25 人群 ALT 升高比例，或者 ADAE 中 SOC 出现频率 top 5。Enter 发送，Shift+Enter 换行。',
)

onMounted(async () => {
  await refreshHistory()
  wsClose = connectProjectWS(props.projectId, (ev) => {
    if (!messages.length) return
    const head = messages[messages.length - 1]
    if (head.status === 'done' || head.status === 'error') return
    if (ev.type === 'analyst.thinking') head.status = 'pending'
    else if (ev.type === 'analyst.code_generated') {
      const p = ev.payload as { plan?: string; code?: string }
      head.plan = p.plan || head.plan
      head.code = p.code || head.code
      head.status = 'code_ready'
    } else if (ev.type === 'analyst.sandbox_running') {
      head.status = 'sandbox_running'
      const p = ev.payload as { run_id?: string }
      if (p.run_id) head.runId = p.run_id
    } else if (ev.type === 'analyst.error') {
      head.status = 'error'
      head.errorMsg = String((ev.payload as { msg?: string }).msg || 'unknown error')
    }
  })
})

onBeforeUnmount(() => wsClose?.())

async function refreshHistory(): Promise<void> {
  try {
    history.value = await getAskHistory(props.projectId)
  } catch { /* ignore */ }
}

function pngUrl(pid: string, runId: string | null, png?: string | null): string | null {
  if (!runId || !png) return null
  const file = String(png).split(/[\\/]/).pop() ?? ''
  return `/api/projects/${pid}/sandbox/runs/${runId}/artifacts/${file}`
}

async function send(): Promise<void> {
  const q = input.value.trim()
  if (!q) return
  sending.value = true
  const msg = reactive<AskMessage>({
    id: `m${Date.now()}`,
    query: q, plan: '', code: '',
    status: 'pending', runId: null,
    statBlock: null,
    stdout: '', stderr: '', artifacts: [],
    chartJson: null, pngUrl: null,
    errorMsg: '',
  })
  messages.push(msg)
  input.value = ''
  try {
    const r = await askData(props.projectId, q)
    msg.statBlock = r.stat_block
    msg.runId = r.sandbox_run_id
    const rj = (r.stat_block.result_json || {}) as Record<string, unknown>
    msg.code = String(rj.sandbox_code || msg.code)
    msg.plan = String(rj.plan || msg.plan)
    msg.stdout = String(rj.stdout_tail || '')
    msg.stderr = String(rj.stderr_tail || '')
    msg.chartJson = (rj.chart_json as Record<string, unknown>) || null
    msg.pngUrl = pngUrl(props.projectId, r.sandbox_run_id, rj.png_path as string | undefined)
    msg.status = 'done'
    emit('stat-block-saved')
    await refreshHistory()
  } catch (e) {
    msg.status = 'error'
    msg.errorMsg = e instanceof Error ? e.message : String(e)
    ElMessage.error('问数据失败')
  } finally {
    sending.value = false
  }
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    void send()
  }
}

function fmtTs(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString()
}

const statusSteps: Array<{ key: AskMessage['status']; label: string }> = [
  { key: 'pending', label: '规划' },
  { key: 'code_ready', label: '代码' },
  { key: 'sandbox_running', label: '运行' },
  { key: 'done', label: '统计块' },
]

function statusIndex(status: AskMessage['status']): number {
  if (status === 'error') return statusSteps.findIndex(s => s.key === 'sandbox_running')
  return Math.max(0, statusSteps.findIndex(s => s.key === status))
}
</script>

<template>
  <section class="data-ask">
    <header>
      <h3>数据问答</h3>
      <span class="muted">M8 · 自然语言 → 沙盒 Python → 表格 + 图表</span>
    </header>

    <div class="stream">
      <div v-for="m in messages" :key="m.id" class="msg">
        <div class="user">{{ m.query }}</div>
        <div class="ask-timeline" :class="{ failed: m.status === 'error' }" aria-label="analysis status">
          <span v-for="(s, i) in statusSteps"
                :key="s.key"
                :class="{ active: i <= statusIndex(m.status), current: i === statusIndex(m.status) }">
            {{ s.label }}
          </span>
        </div>
        <div v-if="m.plan" class="plan">{{ m.plan }}</div>
        <div v-if="m.code" class="card-wrap">
          <CodeRunCard
            :project-id="projectId"
            :code="m.code"
            :initial-stdout="m.stdout"
            :initial-stderr="m.stderr"
            :initial-artifacts="m.artifacts"
            :run-id="m.runId"
          />
        </div>
        <div v-if="m.statBlock?.markdown_table" class="md-block">
          <MdPreview :modelValue="m.statBlock.markdown_table" theme="light"
                     :sanitize="sanitizeMarkdownHtml" />
        </div>
        <div v-if="m.chartJson || m.pngUrl" class="chart-block">
          <EChartsRenderer :option="m.chartJson" :png-url="m.pngUrl" :height="320" />
        </div>
        <div class="footer">
          <el-tag v-if="m.status === 'pending'" type="info" size="small">分析中…</el-tag>
          <el-tag v-else-if="m.status === 'code_ready'" type="warning" size="small">代码生成</el-tag>
          <el-tag v-else-if="m.status === 'sandbox_running'" type="warning" size="small">沙盒运行</el-tag>
          <el-tag v-else-if="m.status === 'done'" type="success" size="small">已保存为 StatBlock</el-tag>
          <el-tag v-else-if="m.status === 'error'" type="danger" size="small">{{ m.errorMsg || '错误' }}</el-tag>
          <span v-if="m.statBlock" class="ref">{{ m.statBlock.ref_code }}</span>
        </div>
      </div>
      <div v-if="!messages.length" class="empty">
        在下方提问一个数据问题，例如「ADAE 中 SOC 出现频率 top 5」。
      </div>
    </div>

    <div v-if="history.length" class="history">
      <h4>历史问答</h4>
      <ul>
        <li v-for="h in history.slice(0, 10)" :key="h.stat_id + h.ts">
          <code>{{ h.stat_id }}</code> · {{ h.query }}
          <span class="muted">· {{ fmtTs(h.ts) }}</span>
        </li>
      </ul>
    </div>

    <div class="composer">
      <textarea v-model="input" :placeholder="placeholder"
                @keydown="onKeydown" rows="3" />
      <el-button type="primary" :loading="sending" @click="send">
        问数据
      </el-button>
    </div>
  </section>
</template>

<style scoped>
.data-ask { border-top: 1px solid var(--color-border); padding: 16px 28px; background: var(--color-surface-2); }
.data-ask header { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.data-ask header h3 { margin: 0; font-size: 15px; color: #1f2937; }
.muted { color: #9ca3af; font-size: 12px; }
.stream { display: flex; flex-direction: column; gap: 16px; max-height: 540px; overflow-y: auto; }
.empty { color: #9ca3af; padding: 20px 0; text-align: center; font-size: 13px; }
.msg { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 6px; padding: 12px 16px; }
.user { font-weight: 600; color: var(--color-text-strong); margin-bottom: 6px; }
.ask-timeline {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 6px;
  margin: 8px 0 10px;
}
.ask-timeline span {
  min-height: 26px;
  border-radius: 999px;
  display: inline-grid;
  place-items: center;
  border: 1px solid var(--color-border);
  color: var(--color-text-mute);
  background: var(--color-surface-2);
  font-size: var(--font-size-xs);
  font-weight: 600;
}
.ask-timeline span.active {
  border-color: color-mix(in srgb, var(--color-primary), var(--color-border) 50%);
  color: var(--color-primary);
  background: var(--color-primary-soft);
}
.ask-timeline span.current {
  box-shadow: inset 0 0 0 1px var(--color-primary);
}
.ask-timeline.failed span.current {
  border-color: var(--color-error);
  color: var(--color-error);
  background: color-mix(in srgb, var(--color-error), transparent 90%);
}
.plan { color: #4b5563; font-size: 13px; padding: 6px 10px; background: #f3f4f6;
        border-left: 3px solid #6366f1; border-radius: 2px; margin-bottom: 10px; }
.card-wrap { margin: 8px 0; }
.md-block { background: #fff; border: 1px solid #e5e7eb; border-radius: 4px;
            padding: 6px 10px; margin: 8px 0; max-height: 320px; overflow-y: auto; }
.chart-block { margin-top: 10px; }
.footer { margin-top: 8px; display: flex; gap: 10px; align-items: center; }
.footer .ref { font-family: ui-monospace, monospace; font-size: 11px; color: #1d4ed8; }
.history { margin: 16px 0 8px; }
.history h4 { font-size: 12px; color: #6b7280; margin: 6px 0; }
.history ul { padding-left: 18px; margin: 0; font-size: 12px; color: #4b5563; }
.history li { margin: 2px 0; }
.composer { display: flex; gap: 10px; margin-top: 14px; }
.composer textarea { flex: 1; padding: 10px 12px; border: 1px solid #d1d5db;
                     border-radius: 4px; font-family: inherit; font-size: 13px;
                     resize: vertical; line-height: 1.5; }
</style>
