<template>
  <div class="heatmap-chart" role="img"
        :aria-label="String($attrs['aria-label'] || 'Heatmap chart of values')">
    <img v-if="imageDataUri" :src="imageDataUri" alt="Heatmap chart" />
    <div v-else ref="chartEl" class="echarts-container" aria-hidden="true" />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'

interface Props { resultJson: Record<string, any> }
const props = defineProps<Props>()
const imageDataUri = computed<string>(() => props.resultJson?.image_data_uri || '')
const chartEl = ref<HTMLElement | null>(null)
let chartInstance: any = null

async function renderECharts() {
  if (imageDataUri.value || !chartEl.value) return
  const echarts = await import('echarts')
  chartInstance = echarts.init(chartEl.value)
  const spec = props.resultJson?.echarts_spec || {}
  chartInstance.setOption({
    tooltip: { position: 'top' },
    grid: { left: 80, top: 30, right: 30, bottom: 60 },
    xAxis: { type: 'category', data: spec.x_labels || [], splitArea: { show: true } },
    yAxis: { type: 'category', data: spec.y_labels || [], splitArea: { show: true } },
    visualMap: {
      min: spec.min ?? 0, max: spec.max ?? 1, calculable: true,
      orient: 'horizontal', left: 'center', bottom: 0,
      inRange: { color: ['#4575b4', '#e0f3f8', '#fee090', '#f46d43', '#d73027'] },
    },
    series: [{ type: 'heatmap', data: spec.data || [], emphasis: { itemStyle: { borderColor: '#000', borderWidth: 1 } } }],
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
.heatmap-chart { display: flex; flex-direction: column; gap: 8px; }
.heatmap-chart img { max-width: 100%; height: auto; border-radius: 4px; }
.echarts-container { width: 100%; height: 360px; }
</style>
