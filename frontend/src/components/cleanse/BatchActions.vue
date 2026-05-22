<script setup lang="ts">
import { ElMessage, ElMessageBox } from 'element-plus'

defineProps<{
  fileId: string
  hasAccepted: boolean
  hasPending: boolean
}>()
const emit = defineEmits<{
  (e: 'apply'): void
  (e: 'accept-all'): void
  (e: 'rollback-latest'): void
}>()

async function confirmAndApply(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '将应用所有「已接受 / 已编辑」规则并写入 processed/，同时创建可回滚快照。',
      '应用清洗规则',
      { confirmButtonText: '应用', cancelButtonText: '取消' },
    )
    emit('apply')
  } catch {
    // user cancelled
    ElMessage.info('已取消')
  }
}

async function confirmAcceptAll(): Promise<void> {
  try {
    await ElMessageBox.confirm(
      '所有 LLM 建议将被标记为已接受。PII 强制项已默认接受。',
      '全部接受',
      { confirmButtonText: '接受', cancelButtonText: '取消' },
    )
    emit('accept-all')
  } catch { /* cancelled */ }
}
</script>

<template>
  <div class="batch">
    <el-button :disabled="!fileId || !hasPending" @click="confirmAcceptAll">
      全部接受 LLM 建议
    </el-button>
    <el-button type="primary" :disabled="!fileId || !hasAccepted" @click="confirmAndApply">
      应用所有已接受规则
    </el-button>
    <el-button :disabled="!fileId" @click="emit('rollback-latest')">
      回滚到最新快照
    </el-button>
  </div>
</template>

<style scoped>
.batch {
  display: flex; gap: 10px; padding: 10px 14px;
  border-top: 1px solid #e5e7eb; background: #fafbfc;
}
</style>
