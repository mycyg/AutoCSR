<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getAlerts, type AlertsPayloadDTO } from '@/api/rest'
import { connectProjectWS } from '@/api/ws'

const props = defineProps<{ projectId: string }>()
const router = useRouter()

const alerts = ref<AlertsPayloadDTO | null>(null)
const expanded = ref(false)
let wsClose: (() => void) | null = null
let autoCollapseTimer: number | null = null

async function refresh(): Promise<void> {
  if (!props.projectId) {
    alerts.value = null
    return
  }
  try {
    alerts.value = await getAlerts(props.projectId)
    // Auto-expand on first error
    if ((alerts.value?.counts.error || 0) > 0 && !expanded.value) {
      expanded.value = true
      if (autoCollapseTimer !== null) window.clearTimeout(autoCollapseTimer)
      autoCollapseTimer = window.setTimeout(() => { expanded.value = false }, 5000)
    }
  } catch {
    alerts.value = null
  }
}

onMounted(() => {
  void refresh()
  if (props.projectId) {
    wsClose = connectProjectWS(props.projectId, (ev) => {
      if (ev.type === 'alerts.updated') {
        void refresh()
      }
    })
  }
})

watch(() => props.projectId, () => {
  wsClose?.()
  wsClose = null
  if (props.projectId) {
    wsClose = connectProjectWS(props.projectId, (ev) => {
      if (ev.type === 'alerts.updated') void refresh()
    })
    void refresh()
  } else {
    alerts.value = null
  }
})

onUnmounted(() => {
  wsClose?.()
  if (autoCollapseTimer !== null) window.clearTimeout(autoCollapseTimer)
})

const counts = computed(() => alerts.value?.counts || { error: 0, warn: 0, info: 0 })
const total = computed(() => counts.value.error + counts.value.warn + counts.value.info)
const items = computed(() => alerts.value?.items || [])

function go(link: string): void {
  if (!link) return
  // app uses hash-style links from backend; just push
  router.push(link)
  expanded.value = false
}
</script>

<template>
  <div v-if="projectId && total > 0" class="alert-bar"
       :class="{ expanded, has_error: counts.error > 0 }">
    <div class="header" @click="expanded = !expanded">
      <span class="chip error" v-if="counts.error">{{ counts.error }} error</span>
      <span class="chip warn" v-if="counts.warn">{{ counts.warn }} warn</span>
      <span class="chip info" v-if="counts.info">{{ counts.info }} info</span>
      <span class="toggle">{{ expanded ? '▴ 收起' : '▾ 展开' }}</span>
    </div>
    <div v-if="expanded" class="list">
      <div v-for="(it, i) in items" :key="i" class="item" :class="it.severity"
           @click="go(it.link as string)">
        <span class="src">{{ it.source }}</span>
        <span class="msg">{{ it.message }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.alert-bar {
  background: #fef9c3; border-bottom: 1px solid #fde68a;
  font-size: 12px; transition: max-height 220ms ease;
}
.alert-bar.has_error { background: #fee2e2; border-bottom-color: #fca5a5; }
.header {
  display: flex; gap: 8px; align-items: center;
  padding: 4px 16px; cursor: pointer;
}
.chip { padding: 1px 8px; border-radius: 10px; color: #fff; font-weight: 500; }
.chip.error { background: #ef4444; }
.chip.warn { background: #f59e0b; }
.chip.info { background: #6b7280; }
.toggle { margin-left: auto; color: #6b7280; font-size: 11px; }
.list { max-height: 260px; overflow: auto; padding: 4px 16px 8px; }
.item {
  padding: 4px 6px; border-radius: 4px; cursor: pointer;
  display: flex; gap: 8px; align-items: center;
}
.item:hover { background: rgba(255,255,255,0.6); }
.item .src {
  font-family: monospace; font-size: 10px; padding: 1px 4px;
  background: rgba(0,0,0,0.06); border-radius: 3px; flex: none;
}
.item.error .src { background: #fecaca; color: #991b1b; }
.item.warn .src { background: #fde68a; color: #92400e; }
.item.info .src { background: #e5e7eb; color: #374151; }
.item .msg { color: #1f2937; }
</style>
