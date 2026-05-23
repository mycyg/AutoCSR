<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listUsers, type UserDTO } from '@/api/rest'

const users = ref<UserDTO[]>([])
const current = ref<string>('demo_author')

const ROLE_LABEL: Record<string, string> = {
  author: '撰写者', reviewer: '审稿人', approver: '审批人', admin: '管理员',
}

onMounted(async () => {
  try {
    users.value = await listUsers()
    const stored = localStorage.getItem('autocsr_user_id')
    if (stored && users.value.some(u => u.id === stored)) {
      current.value = stored
    }
  } catch { /* ignore */ }
})

function onChange(id: string): void {
  current.value = id
  localStorage.setItem('autocsr_user_id', id)
  // Tell axios to send X-User-Id on every request
  import('@/api/rest').then(mod => {
    const api: any = mod.default
    api.defaults.headers.common['X-User-Id'] = id
  })
}
</script>

<template>
  <el-dropdown trigger="click" @command="onChange">
    <span class="trigger">
      <el-avatar :size="22" :icon="'UserFilled'" />
      <span class="name">{{ users.find(u => u.id === current)?.name || current }}</span>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item v-for="u in users" :key="u.id" :command="u.id">
          {{ u.name }} <span class="role">[{{ ROLE_LABEL[u.role] || u.role }}]</span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.trigger { display: flex; align-items: center; gap: 6px; cursor: pointer; }
.name { font-size: 13px; color: #374151; }
.role { color: #9ca3af; font-size: 11px; }
</style>
