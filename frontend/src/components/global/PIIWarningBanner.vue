<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{ projectId: string }>()

interface Finding {
  type: string
  range: [number, number]
  value_masked: string
  confidence: number
}

const visible = ref(false)
const findings = ref<Finding[]>([])
const lastAction = ref<string>('')
let ws: WebSocket | null = null

function connect(): void {
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  ws = new WebSocket(`${proto}://${window.location.host}/ws/${props.projectId}`)
  ws.onmessage = (ev) => {
    try {
      const m = JSON.parse(ev.data)
      if (m.type === 'safety.pii_detected') {
        findings.value = m.payload?.findings || []
        lastAction.value = m.payload?.action || ''
        visible.value = true
      }
    } catch { /* ignore */ }
  }
  ws.onclose = () => {
    setTimeout(connect, 3000)
  }
}

onMounted(connect)
onBeforeUnmount(() => {
  try { ws?.close() } catch { /* ignore */ }
})
</script>

<template>
  <el-alert v-if="visible" type="warning" :closable="true" @close="visible = false"
            show-icon class="pii-banner">
    <template #title>
      检测到 {{ findings.length }} 处 PII（action: {{ lastAction }}）
    </template>
    <template #default>
      <div class="findings">
        <el-tag v-for="(f, i) in findings.slice(0, 10)" :key="i" size="small" type="warning">
          {{ f.type }}: {{ f.value_masked }}
        </el-tag>
        <span v-if="findings.length > 10" class="more">+{{ findings.length - 10 }} more</span>
      </div>
    </template>
  </el-alert>
</template>

<style scoped>
.pii-banner { margin-bottom: 12px; }
.findings { display: flex; gap: 4px; flex-wrap: wrap; }
.more { font-size: 11px; color: #6b7280; align-self: center; }
</style>
