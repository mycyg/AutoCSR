<script setup lang="ts">
import { ref } from 'vue'
import type { ReportStatusDTO } from '@/api/rest'
import AgentStatus from './AgentStatus.vue'
import Terminology from './Terminology.vue'
import ChatPanel from './ChatPanel.vue'

defineProps<{
  projectId: string
  nodeId: string | null
  status: ReportStatusDTO | null
  terminology: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'save-terminology', terms: Record<string, string>): Promise<void> | void
  (e: 'patch-applied'): void
  (e: 'rolled-back', version: number): void
}>()

const tab = ref('chat')
</script>

<template>
  <div class="writer-status">
    <el-tabs v-model="tab" class="tabs">
      <el-tab-pane label="对话编辑" name="chat">
        <ChatPanel :project-id="projectId" :node-id="nodeId"
                   @patch-applied="emit('patch-applied')"
                   @rolled-back="(v) => emit('rolled-back', v)" />
      </el-tab-pane>
      <el-tab-pane label="撰写进度" name="status">
        <AgentStatus :status="status" />
      </el-tab-pane>
      <el-tab-pane label="术语表" name="terms">
        <Terminology :terms="terminology" @save="(t) => emit('save-terminology', t)" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.writer-status { height: 100%; display: flex; flex-direction: column; }
.tabs { height: 100%; display: flex; flex-direction: column; }
.tabs :deep(.el-tabs__content) { flex: 1; overflow: hidden; padding: 0; }
.tabs :deep(.el-tab-pane) { height: 100%; overflow: auto; }
.tabs :deep(.el-tabs__header) { margin: 0 12px; }
</style>
