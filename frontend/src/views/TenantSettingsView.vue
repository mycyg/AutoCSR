<template>
  <main class="tenant-page" role="main" aria-labelledby="tenant-heading">
    <header>
      <h1 id="tenant-heading">{{ tenant?.name || 'Tenant settings' }}</h1>
      <span class="plan" aria-label="Plan tier">{{ tenant?.plan || '—' }}</span>
    </header>

    <section class="card" aria-labelledby="members-heading" role="region">
      <h2 id="members-heading">Members ({{ users.length }})</h2>
      <el-table :data="users" stripe size="default">
        <el-table-column prop="display_name" label="Name" min-width="160" />
        <el-table-column prop="email" label="Email" min-width="220" />
        <el-table-column prop="role" label="Role" width="110">
          <template #default="{ row }">
            <el-tag :type="row.role === 'admin' ? 'danger' : 'info'" effect="plain">
              {{ row.role }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="id" label="User ID" min-width="150">
          <template #default="{ row }">
            <code>{{ row.id }}</code>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <section class="card" aria-labelledby="account-heading" role="region">
      <h2 id="account-heading">Your account</h2>
      <el-form label-position="top" :model="profile" role="form" aria-label="Update profile">
        <el-form-item label="Display name" prop="display_name">
          <el-input v-model="profile.display_name" name="display_name" />
        </el-form-item>
        <el-form-item label="New password (leave blank to keep current)" prop="password">
          <el-input v-model="profile.password" type="password" show-password
                    autocomplete="new-password" name="password" />
        </el-form-item>
        <el-button type="primary" :loading="saving" @click="onSave"
                    aria-label="Save profile changes">Save</el-button>
      </el-form>
    </section>
  </main>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { getTenantInfo, type TenantUserDTO } from '@/api/rest'

const auth = useAuthStore()
const users = ref<TenantUserDTO[]>([])
const tenant = ref<{ id: string; name: string; plan: string } | null>(auth.tenant ? {
  id: auth.tenant.id, name: auth.tenant.name, plan: auth.tenant.plan,
} : null)
const profile = reactive({ display_name: auth.user?.display_name || '', password: '' })
const saving = ref(false)

async function load() {
  try {
    const r = await getTenantInfo()
    tenant.value = r.tenant
    users.value = r.users
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'Failed to load tenant info')
  }
}

async function onSave() {
  saving.value = true
  try {
    await auth.updateMe({
      display_name: profile.display_name || undefined,
      password: profile.password || undefined,
    })
    profile.password = ''
    ElMessage.success('Profile updated')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'Save failed')
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.tenant-page {
  max-width: 980px;
  margin: 0 auto;
  padding: 24px;
}
header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}
header h1 {
  margin: 0;
  font-size: 24px;
  color: #1f2937;
}
.plan {
  background: #eef2ff;
  color: #4338ca;
  padding: 4px 10px;
  border-radius: 99px;
  font-size: 12px;
  text-transform: uppercase;
}
.card {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.card h2 {
  margin-top: 0;
  font-size: 16px;
  color: #1f2937;
}
code {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 12px;
  color: #6b7280;
}
</style>
