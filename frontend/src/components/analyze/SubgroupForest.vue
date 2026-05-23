<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  rows: Array<{ label: string; diff: number; ci_low: number; ci_high: number;
                p_value: number; n_a: number; n_b: number }>
}>()

const range = computed(() => {
  if (!props.rows.length) return { min: -1, max: 1 }
  const lo = Math.min(...props.rows.map((r) => r.ci_low))
  const hi = Math.max(...props.rows.map((r) => r.ci_high))
  const pad = (hi - lo) * 0.1 || 0.5
  return { min: lo - pad, max: hi + pad }
})
function px(v: number): number {
  const { min, max } = range.value
  return ((v - min) / (max - min)) * 100
}
function widthPct(lo: number, hi: number): number {
  return Math.max(0.5, px(hi) - px(lo))
}
</script>

<template>
  <div class="forest">
    <table class="forest-table">
      <thead>
        <tr>
          <th class="lbl">Subgroup</th>
          <th class="n">n(A)/n(B)</th>
          <th class="plot">
            <div class="axis-wrap">
              <span class="axis-min">{{ range.min.toFixed(2) }}</span>
              <span class="axis-zero">0</span>
              <span class="axis-max">{{ range.max.toFixed(2) }}</span>
            </div>
          </th>
          <th class="num">Diff (95% CI)</th>
          <th class="num">p</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.label">
          <td class="lbl">{{ r.label }}</td>
          <td class="n">{{ r.n_a }}/{{ r.n_b }}</td>
          <td class="plot">
            <div class="track">
              <div class="zero-line" :style="{ left: px(0) + '%' }"></div>
              <div class="ci" :style="{ left: px(r.ci_low) + '%', width: widthPct(r.ci_low, r.ci_high) + '%' }"></div>
              <div class="point" :style="{ left: px(r.diff) + '%' }"></div>
            </div>
          </td>
          <td class="num">
            {{ r.diff.toFixed(3) }}
            <span class="muted">[{{ r.ci_low.toFixed(3) }}, {{ r.ci_high.toFixed(3) }}]</span>
          </td>
          <td class="num">{{ r.p_value.toExponential(2) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.forest { font-size: 12px; padding: 6px 0; }
.forest-table { width: 100%; border-collapse: collapse; }
.forest-table th { background: #f3f4f6; color: #1f2937; padding: 6px 8px;
                    text-align: left; border-bottom: 1px solid #e5e7eb; }
.forest-table td { padding: 8px; border-bottom: 1px dashed #e5e7eb; vertical-align: middle; }
.lbl { width: 24%; font-weight: 500; color: #111827; }
.n { width: 8%; color: #4b5563; }
.plot { width: 42%; }
.num { width: 13%; color: #1f2937; font-variant-numeric: tabular-nums; }
.muted { color: #9ca3af; margin-left: 4px; font-size: 11px; }
.track { position: relative; height: 18px; background: #f9fafb; border-radius: 2px; }
.zero-line {
  position: absolute; top: 0; bottom: 0; width: 1px; background: #94a3b8;
  border-left: 1px dashed #94a3b8;
}
.ci { position: absolute; top: 8px; height: 2px; background: #475569; }
.point {
  position: absolute; top: 5px; width: 8px; height: 8px; margin-left: -4px;
  border-radius: 50%; background: #1d4ed8; border: 1px solid #fff;
}
.axis-wrap { display: flex; justify-content: space-between; font-size: 10px; color: #6b7280; }
.axis-zero { color: #94a3b8; }
</style>
