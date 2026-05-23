<template>
  <div class="pk-3d">
    <img v-if="imageDataUri" :src="imageDataUri" alt="PK 3D profile" />
    <div v-else ref="chartEl" class="echarts-container" />
    <p v-if="!imageDataUri" class="hint">
      3D rendering requires <code>echarts-gl</code>. Falls back to 2D scatter when unavailable.
    </p>
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
  // echarts-gl is an optional peer dep; loaded via a variable specifier so
  // Vite/Rollup does not try to resolve it at build time.
  let has3d = true
  const moduleName = 'echarts-gl'
  try {
    // @ts-ignore — optional dep, falls back to 2D when absent
    await import(/* @vite-ignore */ moduleName)
  } catch {
    has3d = false
  }
  chartInstance = echarts.init(chartEl.value)
  const spec = props.resultJson?.echarts_spec || {}
  const data: any[] = spec.data || []
  if (has3d) {
    chartInstance.setOption({
      tooltip: {},
      xAxis3D: { type: 'value', name: spec.x_axis || 'time' },
      yAxis3D: { type: 'value', name: spec.y_axis || 'subject' },
      zAxis3D: { type: 'value', name: spec.z_axis || 'conc' },
      grid3D: { boxWidth: 200, boxDepth: 80, viewControl: { autoRotate: true } },
      series: [{ type: 'scatter3D', data, symbolSize: 6,
                  itemStyle: { color: '#2563eb', opacity: 0.7 } }],
    })
  } else {
    // 2D fallback: project to time × concentration, colour by subject idx
    chartInstance.setOption({
      tooltip: { trigger: 'item' },
      grid: { left: 60, top: 30, right: 30, bottom: 50 },
      xAxis: { type: 'value', name: spec.x_axis || 'time' },
      yAxis: { type: 'value', name: spec.z_axis || 'concentration' },
      series: [{ type: 'scatter', symbolSize: 6, data: data.map((d: any) => [d[0], d[2]]),
                  itemStyle: { color: '#2563eb', opacity: 0.7 } }],
    })
  }
}

onMounted(renderECharts)
watch(() => props.resultJson, () => {
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
  renderECharts()
})
onBeforeUnmount(() => { if (chartInstance) chartInstance.dispose() })
</script>

<style scoped>
.pk-3d { display: flex; flex-direction: column; gap: 8px; }
.pk-3d img { max-width: 100%; height: auto; border-radius: 4px; }
.echarts-container { width: 100%; height: 380px; }
.hint { font-size: 11px; color: #9ca3af; margin: 0; }
.hint code { font-family: monospace; }
</style>
