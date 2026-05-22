<script setup lang="ts">
import { computed } from 'vue'
import type { ReportStatusDTO } from '@/api/rest'

const props = defineProps<{ status: ReportStatusDTO | null }>()

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
</style>
