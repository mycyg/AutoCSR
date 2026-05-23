<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  stages: { screened: number; randomized: number; treated: number; completed: number; discontinued: number }
  arms?: Array<{ arm: string; n_treated: number; n_completed: number; n_discontinued: number }>
  mermaid?: string
}>()

const armList = computed(() => props.arms || [])
</script>

<template>
  <div class="consort">
    <div class="flow-card top">
      <div class="card stage">Screened (n = {{ stages.screened }})</div>
      <div class="arrow">↓</div>
      <div class="card stage">Randomized (n = {{ stages.randomized }})</div>
      <div class="arrow">↓</div>
      <div v-if="armList.length" class="arms-row">
        <div v-for="a in armList" :key="a.arm" class="arm-col">
          <div class="card arm">{{ a.arm }} (n = {{ a.n_treated }})</div>
          <div class="arrow">↓</div>
          <div class="card outcome">
            Completed: {{ a.n_completed }}<br>
            Discontinued: {{ a.n_discontinued }}
          </div>
        </div>
      </div>
      <template v-else>
        <div class="card stage">Treated (n = {{ stages.treated }})</div>
        <div class="arrow">↓</div>
        <div class="card outcome">
          Completed: {{ stages.completed }}<br>
          Discontinued: {{ stages.discontinued }}
        </div>
      </template>
    </div>
    <details v-if="mermaid" class="mermaid-src">
      <summary>查看 mermaid 源码</summary>
      <pre><code>{{ mermaid }}</code></pre>
    </details>
  </div>
</template>

<style scoped>
.consort { padding: 8px 12px; }
.flow-card { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.card {
  background: #dbeafe; border: 1px solid #1e3a8a; border-radius: 6px;
  padding: 8px 14px; min-width: 220px; text-align: center; font-size: 13px;
}
.card.arm { background: #bfdbfe; min-width: 160px; }
.card.outcome { background: #fef3c7; }
.arrow { color: #1e3a8a; font-size: 16px; font-weight: 600; }
.arms-row { display: flex; gap: 24px; justify-content: center; }
.arm-col { display: flex; flex-direction: column; align-items: center; gap: 6px; }
.mermaid-src { margin-top: 16px; font-size: 11px; color: #6b7280; }
.mermaid-src pre {
  background: #f9fafb; border: 1px solid #e5e7eb; padding: 8px 12px;
  border-radius: 4px; overflow: auto; max-height: 240px;
}
</style>
