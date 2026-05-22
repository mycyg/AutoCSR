<script setup lang="ts">
import { computed } from 'vue'
import type { ReportStatusDTO } from '@/api/rest'
import { useReportStore } from '@/stores/report'

const props = defineProps<{ status: ReportStatusDTO | null }>()
const reportStore = useReportStore()

const progress = computed(() => {
  if (!props.status) return 0
  if (!props.status.leaves_total) return 0
  return Math.round((props.status.leaves_done / props.status.leaves_total) * 100)
})

const phaseLabel: Record<string, string> = {
  idle: '空闲',
  background: 'A · 背景 / 方法',
  results: 'B · 结果',
  discussion: 'C · 讨论 / 结论',
  harmonize: 'D · 文风收敛',
  done: '完成',
  error: '错误',
}

const errored = computed(() =>
  (props.status?.sections ?? []).filter((s) => s.status === 'error'),
)

const subPhaseEntries = computed(() =>
  Object.values(reportStore.subPhases).sort((a, b) => b.ts - a.ts).slice(0, 8),
)

const recentTools = computed(() => reportStore.toolCallLog.slice(0, 5))

const dedupHits = computed(() => reportStore.dedupHits.slice(0, 3))

const subPhaseLabel: Record<string, string> = {
  thinking: '思考',
  searching: '检索 corpus',
  'sandbox-running': '沙盒执行',
  'calling-analyst': '调用 analyst',
  drafting: '撰写',
  done: '完成',
  error: '错误',
}

function fmtArgs(v: unknown): string {
  if (!v) return ''
  try {
    const s = JSON.stringify(v)
    return s.length > 120 ? s.slice(0, 120) + '…' : s
  } catch {
    return String(v)
  }
}
</script>

<template>
  <div class="agent-status">
    <template v-if="!status">
      <p class="empty">尚未启动 writer</p>
    </template>
    <template v-else>
      <div class="phase">
        <span class="phase-label">{{ phaseLabel[status.current_phase] ?? status.current_phase }}</span>
        <span v-if="status.harmonized" class="phase-tag">已收敛</span>
      </div>
      <el-progress :percentage="progress" :status="status.current_phase === 'error' ? 'exception'
                                                : status.current_phase === 'done' ? 'success' : ''"
                  :stroke-width="8" />
      <div class="counters">
        <div><span class="k">完成</span> <span class="v">{{ status.leaves_done }} / {{ status.leaves_total }}</span></div>
        <div v-if="status.leaves_errored > 0">
          <span class="k err">错误</span> <span class="v">{{ status.leaves_errored }}</span>
        </div>
        <div><span class="k">总字数</span> <span class="v">{{ status.total_words }}</span></div>
        <div><span class="k">tokens in</span> <span class="v">{{ status.total_tokens.input }}</span></div>
        <div><span class="k">tokens out</span> <span class="v">{{ status.total_tokens.output }}</span></div>
      </div>
      <div v-if="errored.length" class="errors">
        <h4>错误章节</h4>
        <ul>
          <li v-for="s in errored" :key="s.node_id">
            <code>{{ s.node_id }}</code> · {{ s.title }}
            <div v-if="s.error" class="err-msg">{{ s.error }}</div>
          </li>
        </ul>
      </div>
      <div v-if="status.error" class="errors">
        <el-alert type="error" :closable="false">{{ status.error }}</el-alert>
      </div>

      <div v-if="subPhaseEntries.length" class="subphases">
        <h4>writer 子状态</h4>
        <ul>
          <li v-for="e in subPhaseEntries" :key="e.nodeId">
            <code>{{ e.nodeId }}</code> ·
            <span class="phase-pill">{{ subPhaseLabel[e.phase] ?? e.phase }}</span>
            <span v-if="e.toolCall" class="tool-name">{{ e.toolCall }}</span>
          </li>
        </ul>
      </div>

      <div v-if="recentTools.length" class="toolcalls">
        <h4>最近工具调用</h4>
        <ul>
          <li v-for="(c, i) in recentTools" :key="i"
              :class="{ err: c.ok === false }"
              :title="fmtArgs(c.args)">
            <code>{{ c.nodeId }}</code> · {{ c.name }}
            <span v-if="c.durationMs" class="muted">· {{ c.durationMs }}ms</span>
            <span v-if="c.errorMsg" class="muted err">· {{ c.errorMsg }}</span>
          </li>
        </ul>
      </div>

      <div v-if="dedupHits.length" class="dedup">
        <h4>analyst 查询去重</h4>
        <ul>
          <li v-for="(h, i) in dedupHits" :key="i">
            <span class="muted">复用：</span>「{{ h.query }}」
            <span v-if="h.requesters.length" class="muted">
              · {{ h.requesters.join(', ') }}
            </span>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.agent-status { display: flex; flex-direction: column; gap: 12px; font-size: 12px; }
.empty { color: #9ca3af; }
.phase { display: flex; align-items: baseline; gap: 8px; }
.phase-label { font-weight: 600; color: #1f2937; font-size: 13px; }
.phase-tag { font-size: 11px; padding: 1px 6px; background: #ecfdf5; color: #047857; border-radius: 8px; }
.counters { display: grid; grid-template-columns: 1fr 1fr; row-gap: 6px; column-gap: 12px; }
.counters .k { color: #6b7280; }
.counters .k.err { color: #dc2626; }
.counters .v { font-family: ui-monospace, monospace; color: #111827; }
.errors h4 { margin: 6px 0 4px; font-size: 12px; color: #374151; }
.errors ul { margin: 0; padding-left: 16px; }
.err-msg { color: #ef4444; font-size: 11px; }
.subphases, .toolcalls, .dedup { margin-top: 6px; border-top: 1px dashed #e5e7eb; padding-top: 6px; }
.subphases h4, .toolcalls h4, .dedup h4 { margin: 4px 0; font-size: 11px; color: #6b7280; font-weight: 500; }
.subphases ul, .toolcalls ul, .dedup ul { padding-left: 14px; margin: 0; font-size: 11px; }
.phase-pill { display: inline-block; padding: 0 6px; border-radius: 8px; background: #eef2ff; color: #4338ca; }
.tool-name { margin-left: 6px; font-family: ui-monospace, monospace; color: #047857; }
.toolcalls li { cursor: help; padding: 1px 0; }
.toolcalls li.err { color: #b91c1c; }
.muted { color: #9ca3af; }
.muted.err { color: #ef4444; }
</style>
