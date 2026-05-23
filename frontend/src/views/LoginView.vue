<template>
  <div class="auth-wrap">
    <div class="auth-card">
      <h1>AutoCSR</h1>
      <p class="subtitle">Sign in to continue</p>
      <el-form :model="form" @submit.prevent="onSubmit" label-position="top" size="large">
        <el-form-item label="Email">
          <el-input v-model="form.email" placeholder="you@example.com" autocomplete="email" />
        </el-form-item>
        <el-form-item label="Password">
          <el-input v-model="form.password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-alert v-if="auth.error" type="error" :title="auth.error" :closable="false" class="auth-err" />
        <el-button type="primary" native-type="submit" :loading="auth.loading" class="auth-submit">
          Sign in
        </el-button>
      </el-form>
      <p class="auth-footer">
        New here?
        <router-link to="/register">Create an account</router-link>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const form = reactive({ email: '', password: '' })

async function onSubmit() {
  try {
    await auth.login(form.email.trim(), form.password)
    const next = (route.query.next as string) || '/'
    router.replace(next)
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
  width: 380px;
  background: #fff;
  border-radius: 12px;
  padding: 32px 28px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.06);
}
.auth-card h1 {
  margin: 0 0 4px;
  font-size: 28px;
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
