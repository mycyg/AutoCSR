<script setup lang="ts">
import { ref } from 'vue'
import type { ReportStatusDTO } from '@/api/rest'
import AgentStatus from './AgentStatus.vue'
import Terminology from './Terminology.vue'

defineProps<{
  status: ReportStatusDTO | null
  terminology: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'save-terminology', terms: Record<string, string>): Promise<void> | void
}>()

const tab = ref('status')
</script>

<template>
  <div class="writer-status">
    <el-tabs v-model="tab" class="tabs">
      <el-tab-pane label="Agent 状态" name="status">
        <AgentStatus :status="status" />
      </el-tab-pane>
      <el-tab-pane label="术语表" name="terms">
        <Terminology :terms="terminology" @save="(t) => emit('save-terminology', t)" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.writer-status { height: 100%; padding: 8px 12px; overflow: auto; }
.tabs { height: 100%; }
</style>
