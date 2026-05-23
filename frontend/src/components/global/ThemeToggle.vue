<script setup lang="ts">
/**
 * Theme toggle button (top bar).
 */
import { useTheme } from '@/composables/useTheme'
import { useI18n } from 'vue-i18n'

const { isDark, toggleTheme } = useTheme()
const { t } = useI18n()
</script>

<template>
  <el-button text class="theme-toggle"
              :aria-label="isDark ? t('theme.to_light') : t('theme.to_dark')"
              @click="toggleTheme">
    <span aria-hidden="true">{{ isDark ? '☀' : '☾' }}</span>
  </el-button>
</template>

<style scoped>
.theme-toggle {
  font-size: 18px;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  color: var(--color-text-mute);
}
.theme-toggle:hover { background: var(--color-surface-3); color: var(--color-primary); }
</style>
