<template>
  <div class="auth-wrap">
    <main class="auth-card" role="main" aria-labelledby="login-heading">
      <h1 id="login-heading">AutoCSR</h1>
      <p class="subtitle">Sign in to continue</p>
      <el-form :model="form" @submit.prevent="onSubmit" label-position="top" size="large"
                role="form" aria-label="Sign-in form">
        <el-form-item label="Email" prop="email">
          <el-input v-model="form.email" placeholder="you@example.com" autocomplete="email"
                    aria-required="true" name="email" type="email" />
        </el-form-item>
        <el-form-item label="Password" prop="password">
          <el-input v-model="form.password" type="password" show-password autocomplete="current-password"
                    aria-required="true" name="password" />
        </el-form-item>
        <el-alert v-if="auth.error" type="error" :title="auth.error" :closable="false" class="auth-err"
                   role="alert" aria-live="assertive" />
        <el-button type="primary" native-type="submit" :loading="auth.loading" class="auth-submit"
                    aria-label="Sign in to AutoCSR">
          Sign in
        </el-button>
      </el-form>
      <p class="auth-footer">
        New here?
        <router-link to="/register">Create an account</router-link>
      </p>
    </main>
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
  background: var(--color-bg);
}
.auth-card {
  width: 380px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 32px 28px;
}
.auth-card h1 {
  margin: 0 0 4px;
  font-size: 28px;
  color: var(--color-text);
  font-weight: 600;
}
.subtitle {
  margin: 0 0 24px;
  color: var(--color-text-mute);
  font-size: 15px;
}
@media (max-width: 767px) {
  .auth-card { width: 92vw; padding: 24px 18px; }
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
  color: var(--color-text-mute);
  font-size: 13px;
}
.auth-footer a {
  color: var(--color-primary);
  text-decoration: none;
}
</style>
