<template>
  <el-dialog v-model="visible" title="Project members" width="640px">
    <el-table :data="members" size="small" stripe>
      <el-table-column label="Member" min-width="180">
        <template #default="{ row }">
          <div>
            <div>{{ row.user?.display_name || row.user_id }}</div>
            <div class="email">{{ row.user?.email || '' }}</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="Role" width="160">
        <template #default="{ row }">
          <el-select v-model="row.role" size="small" @change="onChangeRole(row)">
            <el-option label="Owner" value="owner" />
            <el-option label="Editor" value="editor" />
            <el-option label="Reviewer" value="reviewer" />
            <el-option label="Viewer" value="viewer" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="" width="80">
        <template #default="{ row }">
          <el-button text type="danger" size="small" @click="onRemove(row)">Remove</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-divider />
    <h4 style="margin: 8px 0;">Invite from your tenant</h4>
    <div class="invite-row">
      <el-select v-model="inviteUserId" placeholder="Pick user" filterable size="small" style="flex:1">
        <el-option v-for="u in inviteCandidates" :key="u.id"
                    :label="`${u.display_name} (${u.email})`" :value="u.id" />
      </el-select>
      <el-select v-model="inviteRole" size="small" style="width: 130px">
        <el-option label="Owner" value="owner" />
        <el-option label="Editor" value="editor" />
        <el-option label="Reviewer" value="reviewer" />
        <el-option label="Viewer" value="viewer" />
      </el-select>
      <el-button type="primary" size="small" :loading="busy" :disabled="!inviteUserId"
                  @click="onInvite">Add</el-button>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  addProjectMember, getTenantInfo, listProjectMembers, patchProjectMember,
  removeProjectMember, type ProjectMemberDTO, type TenantUserDTO,
} from '@/api/rest'

const props = defineProps<{ modelValue: boolean; projectId: string }>()
const emit = defineEmits<{ 'update:modelValue': [boolean] }>()
const visible = computed({
  get: () => props.modelValue, set: (v: boolean) => emit('update:modelValue', v),
})

const members = ref<ProjectMemberDTO[]>([])
const tenantUsers = ref<TenantUserDTO[]>([])
const inviteUserId = ref('')
const inviteRole = ref<'owner' | 'editor' | 'reviewer' | 'viewer'>('editor')
const busy = ref(false)

const inviteCandidates = computed(() => {
  const ids = new Set(members.value.map(m => m.user_id))
  return tenantUsers.value.filter(u => !ids.has(u.id))
})

async function refresh() {
  try {
    members.value = await listProjectMembers(props.projectId)
    const t = await getTenantInfo()
    tenantUsers.value = t.users
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'Failed to load members')
  }
}

async function onChangeRole(row: ProjectMemberDTO) {
  busy.value = true
  try {
    await patchProjectMember(props.projectId, row.user_id, row.role)
    ElMessage.success(`Updated ${row.user_id}`)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'Update failed')
    await refresh()
  } finally {
    busy.value = false
  }
}

async function onRemove(row: ProjectMemberDTO) {
  busy.value = true
  try {
    await removeProjectMember(props.projectId, row.user_id)
    ElMessage.success(`Removed ${row.user_id}`)
    await refresh()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'Remove failed')
  } finally {
    busy.value = false
  }
}

async function onInvite() {
  busy.value = true
  try {
    await addProjectMember(props.projectId, inviteUserId.value, inviteRole.value)
    inviteUserId.value = ''
    inviteRole.value = 'editor'
    ElMessage.success('Member added')
    await refresh()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'Add failed')
  } finally {
    busy.value = false
  }
}

watch(visible, (v) => { if (v) refresh() })
</script>

<style scoped>
.email {
  font-size: 11px;
  color: #6b7280;
}
.invite-row {
  display: flex;
  gap: 8px;
}
</style>
