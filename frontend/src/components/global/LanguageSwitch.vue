<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { setLocale, type Locale } from '@/i18n'

const { locale } = useI18n()
const current = computed<Locale>(() => (locale.value as Locale))

function pick(l: Locale): void {
  setLocale(l)
}
</script>

<template>
  <el-dropdown trigger="click" @command="pick">
    <span class="lang-switch" :title="$t('common.language')">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none"
           stroke="currentColor" stroke-width="1.6" aria-hidden="true">
        <circle cx="12" cy="12" r="9"/>
        <path d="M3 12h18M12 3a14 14 0 010 18M12 3a14 14 0 000 18"/>
      </svg>
      <span class="code">{{ current.toUpperCase() }}</span>
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="zh" :disabled="current === 'zh'">简体中文</el-dropdown-item>
        <el-dropdown-item command="en" :disabled="current === 'en'">English</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.lang-switch {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  color: #6b7280;
  padding: 4px 8px;
  border-radius: 6px;
  transition: background 120ms ease, color 120ms ease;
}
.lang-switch:hover { background: #f3f4f6; color: #1f2937; }
.code { font-size: 12px; font-weight: 600; letter-spacing: 0.5px; }
</style>
