<script setup lang="ts">
import { ref, watch } from 'vue'
import type { ReportStatusDTO } from '@/api/rest'
import AgentStatus from './AgentStatus.vue'
import Terminology from './Terminology.vue'
import ChatPanel from './ChatPanel.vue'
import PlanPanel from './PlanPanel.vue'
import CommentsPanel from './CommentsPanel.vue'
import MarkerToolbar from './MarkerToolbar.vue'
import DiffView from './DiffView.vue'

const props = defineProps<{
  projectId: string
  nodeId: string | null
  outlineTitle?: string | null
  status: ReportStatusDTO | null
  terminology: Record<string, string>
  activeTab?: string | null
}>()

const emit = defineEmits<{
  (e: 'save-terminology', terms: Record<string, string>): Promise<void> | void
  (e: 'patch-applied'): void
  (e: 'rolled-back', version: number): void
  (e: 'refined'): void
  (e: 'comments-applied'): void
}>()

const tab = ref('chat')

watch(() => props.activeTab, (next) => {
  if (next && ['plan', 'chat', 'comments', 'markers', 'diff', 'status', 'terms'].includes(next)) {
    tab.value = next
  }
}, { immediate: true })
</script>

<template>
  <div class="writer-status">
    <el-tabs v-model="tab" class="tabs">
      <el-tab-pane label="Plan" name="plan" lazy>
        <PlanPanel :project-id="projectId" :node-id="nodeId"
                   :outline-title="outlineTitle"
                   @refined="emit('refined')" />
      </el-tab-pane>
      <el-tab-pane label="对话" name="chat">
        <ChatPanel :project-id="projectId" :node-id="nodeId"
                   @patch-applied="emit('patch-applied')"
                   @rolled-back="(v) => emit('rolled-back', v)" />
      </el-tab-pane>
      <el-tab-pane label="批注" name="comments">
        <CommentsPanel :project-id="projectId" :node-id="nodeId"
                        @applied="emit('comments-applied')" />
      </el-tab-pane>
      <el-tab-pane label="标记" name="markers">
        <MarkerToolbar :project-id="projectId" :node-id="nodeId" />
      </el-tab-pane>
      <el-tab-pane label="Diff" name="diff">
        <DiffView :project-id="projectId" :node-id="nodeId" />
      </el-tab-pane>
      <el-tab-pane label="进度" name="status">
        <AgentStatus :status="status" />
      </el-tab-pane>
      <el-tab-pane label="术语" name="terms">
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
.tabs :deep(.el-tabs__nav) { font-size: 12px; }
.tabs :deep(.el-tabs__item) { padding: 0 10px; height: 36px; line-height: 36px; }
</style>
