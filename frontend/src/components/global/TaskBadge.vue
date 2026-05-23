<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { listTasks } from '@/api/rest'

const props = defineProps<{ projectId: string }>()
const openCount = ref(0)

async function refresh(): Promise<void> {
  try {
    const me = localStorage.getItem('autocsr_user_id') || 'demo_author'
    const tasks = await listTasks(props.projectId, { assignee: me, status: 'open' })
    openCount.value = tasks.length
  } catch { /* ignore */ }
}

onMounted(refresh)
watch(() => props.projectId, refresh)

const visible = computed(() => openCount.value > 0)
</script>

<template>
  <el-badge v-if="visible" :value="openCount" type="danger" />
</template>
