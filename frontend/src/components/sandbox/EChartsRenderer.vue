<script setup lang="ts">
/**
 * Render an arbitrary ECharts option object (server-side `chart_json`)
 * inside a `<div>`. Falls back to a static `<img>` tag if the consumer
 * only has a PNG URL.
 *
 * Listens for window resize so the chart stays responsive inside the
 * three-column layout.
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as echarts from 'echarts'

const props = defineProps<{
  option: Record<string, unknown> | null
  pngUrl?: string | null
  height?: number
}>()

const host = ref<HTMLDivElement | null>(null)
let chart: echarts.ECharts | null = null
let ro: ResizeObserver | null = null

function render(): void {
  if (!host.value || !props.option) return
  if (!chart) chart = echarts.init(host.value)
  chart.setOption(props.option as never, true)
  chart.resize()
}

function teardown(): void {
  if (chart) {
    chart.dispose()
    chart = null
  }
  if (ro) { ro.disconnect(); ro = null }
}

onMounted(() => {
  if (props.option) render()
  if (host.value && 'ResizeObserver' in window) {
    ro = new ResizeObserver(() => chart?.resize())
    ro.observe(host.value)
  }
})

onBeforeUnmount(teardown)

watch(() => props.option, () => {
  if (!props.option) {
    teardown()
  } else {
    render()
  }
}, { deep: true })
</script>

<template>
  <div class="echarts-wrap" :style="{ height: (height ?? 320) + 'px' }">
    <div v-if="option" ref="host" class="echarts-host" />
    <img v-else-if="pngUrl" :src="pngUrl" class="png-fallback" />
    <div v-else class="empty">无图表</div>
  </div>
</template>

<style scoped>
.echarts-wrap { width: 100%; }
.echarts-host { width: 100%; height: 100%; }
.png-fallback { max-width: 100%; max-height: 100%; object-fit: contain; }
.empty { color: #9ca3af; text-align: center; padding: 36px 0; font-size: 12px; }
</style>
