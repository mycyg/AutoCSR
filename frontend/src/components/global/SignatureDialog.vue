<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { signArtifact, type SignatureDTO } from '@/api/rest'

const props = defineProps<{
  modelValue: boolean
  projectId: string
  artifactType: string
  artifactId: string
  defaultSigner?: string
}>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'signed', sig: SignatureDTO): void
}>()

const reason = ref('')
const signer = ref(props.defaultSigner || 'demo_approver')
const loading = ref(false)

watch(() => props.modelValue, (v) => {
  if (v) {
    reason.value = ''
    signer.value = props.defaultSigner || 'demo_approver'
  }
})

async function submit(): Promise<void> {
  if (!reason.value.trim()) {
    ElMessage.warning('请填写签名原因')
    return
  }
  loading.value = true
  try {
    const sig = await signArtifact(props.projectId, {
      artifact_type: props.artifactType,
      artifact_id: props.artifactId,
      reason: reason.value,
      signer: signer.value,
    })
    emit('signed', sig)
    emit('update:modelValue', false)
    ElMessage.success(`已签名 ${sig.id} (${sig.algorithm})`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-dialog :model-value="modelValue" @update:model-value="emit('update:modelValue', $event)"
              title="电子签名" width="480">
    <el-form label-width="80px">
      <el-form-item label="Artifact">
        <code>{{ artifactType }} / {{ artifactId }}</code>
      </el-form-item>
      <el-form-item label="Signer">
        <el-select v-model="signer">
          <el-option value="demo_author" label="撰写者 Author Demo" />
          <el-option value="demo_reviewer" label="审稿人 Reviewer Demo" />
          <el-option value="demo_approver" label="审批人 Approver Demo" />
          <el-option value="demo_admin" label="管理员 Admin Demo" />
        </el-select>
      </el-form-item>
      <el-form-item label="原因">
        <el-input v-model="reason" type="textarea" :rows="3" placeholder="例如：Final approval" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :loading="loading" @click="submit">签名</el-button>
    </template>
  </el-dialog>
</template>
