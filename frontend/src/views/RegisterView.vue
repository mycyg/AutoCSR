<template>
  <div class="auth-wrap">
    <div class="auth-card">
      <h1>Create your account</h1>
      <p class="subtitle">Start a new tenant or join the default workspace</p>
      <el-form :model="form" @submit.prevent="onSubmit" label-position="top" size="large">
        <el-form-item label="Email">
          <el-input v-model="form.email" placeholder="you@example.com" autocomplete="email" />
        </el-form-item>
        <el-form-item label="Display name">
          <el-input v-model="form.display_name" placeholder="Ada Lovelace" />
        </el-form-item>
        <el-form-item label="Password (min 6 chars)">
          <el-input v-model="form.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="Tenant / Organisation name (optional)">
          <el-input v-model="form.tenant_name" placeholder="Leave blank to join the default tenant" />
        </el-form-item>
        <el-alert v-if="auth.error" type="error" :title="auth.error" :closable="false" class="auth-err" />
        <el-button type="primary" native-type="submit" :loading="auth.loading" class="auth-submit">
          Create account
        </el-button>
      </el-form>
      <p class="auth-footer">
        Already have an account?
        <router-link to="/login">Sign in</router-link>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const form = reactive({
  email: '', password: '', display_name: '', tenant_name: '',
})

async function onSubmit() {
  try {
    await auth.register({
      email: form.email.trim(),
      password: form.password,
      display_name: form.display_name.trim() || undefined,
      tenant_name: form.tenant_name.trim() || undefined,
    })
    router.replace('/')
  } catch {
    /* error already in auth.error */
  }
}
</script>

<style scoped>
.auth-wrap {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #f3f7ff, #eaf3ff);
}
.auth-card {
  width: 420px;
  background: #fff;
  border-radius: 12px;
  padding: 32px 28px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
}
.auth-card h1 {
  margin: 0 0 4px;
  font-size: 26px;
  color: #1f2937;
}
.subtitle {
  margin: 0 0 24px;
  color: #6b7280;
  font-size: 14px;
}
.auth-err {
  margin-bottom: 12px;
}
.auth-submit {
  width: 100%;
}
.auth-footer {
  margin-top: 18px;
  text-align: center;
  color: #6b7280;
  font-size: 13px;
}
.auth-footer a {
  color: #2563eb;
  text-decoration: none;
}
</style>
