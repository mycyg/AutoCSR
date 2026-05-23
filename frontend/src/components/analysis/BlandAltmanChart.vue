<template>
  <div class="ba-chart">
    <img v-if="imageDataUri" :src="imageDataUri" alt="Bland-Altman plot" />
    <div v-else ref="chartEl" class="echarts-container" />
    <ul class="stats">
      <li><b>n:</b> {{ resultJson.n_pairs }}</li>
      <li><b>bias:</b> {{ format(resultJson.bias) }}</li>
      <li><b>±1.96 SD:</b> {{ format(resultJson.lower_LoA) }} → {{ format(resultJson.upper_LoA) }}</li>
    </ul>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'

interface Props { resultJson: Record<string, any> }
const props = defineProps<Props>()
const imageDataUri = computed<string>(() => props.resultJson?.image_data_uri || '')
const chartEl = ref<HTMLElement | null>(null)
let chartInstance: any = null

function format(v: any): string {
  if (typeof v === 'number') return v.toFixed(3)
  return String(v ?? '')
}

async function renderECharts() {
  if (imageDataUri.value || !chartEl.value) return
  const echarts = await import('echarts')
  chartInstance = echarts.init(chartEl.value)
  const spec = props.resultJson?.echarts_spec || {}
  chartInstance.setOption({
    title: { text: 'Bland-Altman plot', left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'item' },
    grid: { left: 60, right: 20, top: 40, bottom: 50 },
    xAxis: { type: 'value', name: 'Mean of two methods' },
    yAxis: { type: 'value', name: 'Difference' },
    series: [
      { type: 'scatter', data: spec.scatter || [], itemStyle: { color: '#3b82f6' }, symbolSize: 6 },
      { type: 'line', markLine: { silent: true, symbol: 'none', data: [
        { yAxis: spec.bias, label: { formatter: 'bias' }, lineStyle: { color: '#374151' } },
        { yAxis: spec.upper_LoA, label: { formatter: '+1.96 SD' }, lineStyle: { color: '#ef4444', type: 'dashed' } },
        { yAxis: spec.lower_LoA, label: { formatter: '-1.96 SD' }, lineStyle: { color: '#ef4444', type: 'dashed' } },
      ]}, data: [] },
    ],
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
.ba-chart { display: flex; flex-direction: column; gap: 8px; }
.ba-chart img { max-width: 100%; height: auto; border-radius: 4px; }
.echarts-container { width: 100%; height: 320px; }
.stats { list-style: none; padding: 0; display: flex; gap: 18px; font-size: 12px; color: #4b5563; }
.stats li b { color: #1f2937; }
</style>
