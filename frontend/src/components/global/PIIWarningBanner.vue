<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { connectProjectWS } from '@/api/ws'

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
let wsClose: (() => void) | null = null

function connect(): void {
  wsClose?.()
  wsClose = null
  findings.value = []
  visible.value = false
  if (!props.projectId) return
  wsClose = connectProjectWS(props.projectId, (m) => {
    if (m.type === 'safety.pii_detected') {
      findings.value = (m.payload?.findings as Finding[] | undefined) || []
      lastAction.value = String(m.payload?.action || '')
      visible.value = true
    }
  })
}

onMounted(connect)
watch(() => props.projectId, connect)
onBeforeUnmount(() => {
  wsClose?.()
  wsClose = null
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
