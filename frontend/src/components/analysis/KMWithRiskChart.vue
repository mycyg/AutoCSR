<template>
  <div class="km-risk-chart">
    <img v-if="imageDataUri" :src="imageDataUri" alt="KM with risk table" />
    <div v-else ref="chartEl" class="echarts-container" />
    <div v-if="riskRows.length" class="risk-table-summary">
      <table>
        <thead>
          <tr>
            <th>Group</th>
            <th v-for="t in timePoints" :key="t">{{ t }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in riskRows" :key="row.group">
            <td>{{ row.group }}</td>
            <td v-for="(n, i) in row.n_at_risk" :key="i">{{ n }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'

interface Props {
  resultJson: Record<string, any>
}
const props = defineProps<Props>()
const imageDataUri = computed<string>(() => props.resultJson?.image_data_uri || '')
const timePoints = computed<number[]>(() => props.resultJson?.risk_table?.time_points || [])
const riskRows = computed<{ group: string; n_at_risk: number[] }[]>(
  () => props.resultJson?.risk_table?.rows || [],
)

const chartEl = ref<HTMLElement | null>(null)
let chartInstance: any = null

async function renderECharts() {
  if (imageDataUri.value) return
  if (!chartEl.value) return
  const echarts = await import('echarts')
  chartInstance = echarts.init(chartEl.value)
  const groups = props.resultJson?.echarts_spec?.groups || []
  const series = groups.map((g: any) => ({
    name: g.name, type: 'line', step: 'end', showSymbol: false,
    data: (g.data || []).map((p: [number, number]) => [p[0], p[1]]),
  }))
  chartInstance.setOption({
    title: { text: 'Kaplan-Meier survival', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' },
    legend: { bottom: 0 },
    grid: { left: 50, right: 30, top: 40, bottom: 60 },
    xAxis: { type: 'value', name: 'Time' },
    yAxis: { type: 'value', name: 'S(t)', min: 0, max: 1 },
    series,
  })
}

onMounted(renderECharts)
watch(() => props.resultJson, () => {
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
  renderECharts()
})
onBeforeUnmount(() => { if (chartInstance) chartInstance.dispose() })
</script>

<style scoped>
.km-risk-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.km-risk-chart img {
  max-width: 100%;
  height: auto;
  border-radius: 4px;
}
.echarts-container {
  width: 100%;
  height: 360px;
}
.risk-table-summary table {
  width: 100%;
  font-size: 12px;
  border-collapse: collapse;
}
.risk-table-summary th, .risk-table-summary td {
  padding: 4px 8px;
  text-align: center;
  border: 1px solid #e5e7eb;
}
.risk-table-summary th {
  background: #f3f4f6;
}
</style>
