<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'

interface StepDef {
  key: string
  i18nKey: string
  path: string
}

interface StepCounters {
  done?: number
  pending?: number
  error?: number
  info?: number
}

interface StateSummary {
  steps: Record<string, StepCounters>
  current_step: string
}

const props = defineProps<{
  steps: StepDef[]
  projectId: string
  activeKey: string
}>()

const emit = defineEmits<{
  (e: 'go', step: StepDef): void
}>()

const summary = ref<StateSummary | null>(null)
let timer: number | null = null

async function refresh(): Promise<void> {
  if (!props.projectId) {
    summary.value = null
    return
  }
  try {
    const r = await axios.get<StateSummary>(`/api/projects/${props.projectId}/state_summary`)
    summary.value = r.data
  } catch {
    summary.value = null
  }
}

onMounted(() => {
  void refresh()
  timer = window.setInterval(() => void refresh(), 10_000)
})

onUnmounted(() => {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
})

watch(() => props.projectId, () => { void refresh() })

function counters(key: string): StepCounters {
  return summary.value?.steps?.[key] || {}
}

function badge(key: string): { text: string; type: 'info' | 'warning' | 'danger' | 'success' } | null {
  const c = counters(key)
  if (c.error && c.error > 0) return { text: String(c.error), type: 'danger' }
  if (c.pending && c.pending > 0) return { text: String(c.pending), type: 'warning' }
  if (c.done && c.done > 0) return { text: String(c.done), type: 'success' }
  return null
}

function summaryText(key: string): string {
  const c = counters(key)
  const parts: string[] = []
  if (c.done !== undefined) parts.push(`done=${c.done}`)
  if (c.pending !== undefined) parts.push(`pending=${c.pending}`)
  if (c.error !== undefined && c.error > 0) parts.push(`error=${c.error}`)
  return parts.join(' · ') || '—'
}

const currentStep = computed(() => summary.value?.current_step || '')
const currentStepNeedsNext = computed(() => {
  const k = currentStep.value
  if (!k) return false
  const c = counters(k)
  return (c.done || 0) === 0 && (c.pending || 0) === 0
})

function isCurrent(key: string): boolean {
  return key === currentStep.value
}

function go(step: StepDef): void {
  emit('go', step)
}
</script>

<template>
  <nav class="steps">
    <template v-for="(s, i) in steps" :key="s.key">
      <el-tooltip placement="bottom" :show-after="180" effect="light">
        <template #content>
          <div class="tip">
            <div class="tip-title">{{ $t(s.i18nKey) }}</div>
            <div class="tip-row">{{ summaryText(s.key) }}</div>
            <div v-if="isCurrent(s.key) && currentStepNeedsNext" class="tip-hint">
              {{ $t('steps.next_hint') }}
            </div>
          </div>
        </template>
        <button type="button"
              class="step"
              :class="{
                active: activeKey === s.key,
                disabled: !projectId,
                'is-current': isCurrent(s.key) && activeKey !== s.key,
              }"
              :disabled="!projectId"
              @click="go(s)">
          <span class="num">{{ i + 1 }}</span>
          <span class="label">{{ $t(s.i18nKey) }}</span>
          <el-badge v-if="badge(s.key)"
                    :value="badge(s.key)!.text"
                    :type="badge(s.key)!.type"
                    class="step-badge" />
        </button>
      </el-tooltip>
    </template>
  </nav>
</template>

<style scoped>
.steps {
  display: flex;
  gap: 8px;
  min-width: max-content;
  color: var(--color-text-muted);
  font-size: 13px;
  white-space: nowrap;
}
.step {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 12px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  transition: background 120ms ease;
  white-space: nowrap;
}
.step:hover:not(.disabled) { background: var(--color-surface-muted); color: var(--color-text-strong); }
.step.active { background: var(--color-primary-soft); color: var(--color-primary); }
.step.is-current::after {
  content: '';
  position: absolute;
  left: 8px; right: 8px; bottom: -3px;
  height: 2px;
  background: linear-gradient(90deg, var(--color-primary), var(--color-info));
  border-radius: 2px;
  opacity: 0.7;
}
.step.disabled { cursor: not-allowed; opacity: 0.45; }
.step .num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 20px; height: 20px;
  border-radius: 50%;
  background: var(--color-surface-muted);
  font-size: 11px;
}
.step.active .num { background: var(--color-primary); color: #fff; }
.step-badge { margin-left: 4px; }
.step-badge :deep(.el-badge__content) { transform: translate(0, 0); position: static; }
.tip-title { font-weight: 600; color: var(--color-text-strong); font-size: 12px; }
.tip-row { color: var(--color-text); font-size: 12px; margin-top: 2px; }
.tip-hint { color: var(--color-primary); font-size: 12px; margin-top: 4px; }
</style>
