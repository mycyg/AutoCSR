<template>
  <el-dropdown trigger="click" @command="onCommand">
    <span class="user-avatar">
      <span class="avatar-circle">{{ initials }}</span>
      <span class="user-meta">
        <span class="user-name">{{ auth.user?.display_name || 'Guest' }}</span>
        <span class="tenant-name">{{ auth.tenant?.name || '—' }}</span>
      </span>
      <el-icon class="caret"><ArrowDown /></el-icon>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item disabled>
          <span class="email">{{ auth.user?.email || '' }}</span>
        </el-dropdown-item>
        <el-dropdown-item divided command="tenant">Tenant settings</el-dropdown-item>
        <el-dropdown-item command="profile">Account profile</el-dropdown-item>
        <el-dropdown-item divided command="logout">Sign out</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowDown } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const initials = computed(() => {
  const n = auth.user?.display_name || auth.user?.email || '?'
  return n.slice(0, 2).toUpperCase()
})

async function onCommand(cmd: string | number | object) {
  if (cmd === 'logout') {
    await auth.logout()
    router.replace('/login')
  } else if (cmd === 'tenant' || cmd === 'profile') {
    router.push('/tenant/settings')
  }
}
</script>

<style scoped>
.user-avatar {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 0.15s;
}
.user-avatar:hover {
  background: rgba(0, 0, 0, 0.04);
}
.avatar-circle {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  font-size: 11px;
  font-weight: 600;
  display: grid;
  place-items: center;
}
.user-meta {
  display: flex;
  flex-direction: column;
  font-size: 12px;
  line-height: 1.2;
}
.user-name {
  font-weight: 600;
  color: #1f2937;
}
.tenant-name {
  color: #6b7280;
  font-size: 10px;
}
.caret {
  color: #9ca3af;
  font-size: 12px;
}
.email {
  color: #6b7280;
  font-size: 12px;
}
</style>
