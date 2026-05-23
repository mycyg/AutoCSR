<script setup lang="ts">
/**
 * Top-bar "?" help dropdown.
 *
 * Each item dispatches a custom event so the relevant global modal
 * (ShortcutsHelpModal / OnboardingTour) can pop up. Documentation
 * links open externally.
 */
import { triggerShortcut } from '@/composables/useShortcuts'

function openOnboarding(): void {
  window.dispatchEvent(new CustomEvent('autocsr:onboarding:open'))
}
function openShortcuts(): void {
  triggerShortcut('help')
}
function openDocs(): void {
  window.open('https://github.com/your-org/AutoCSR#readme', '_blank', 'noopener')
}
function openChangelog(): void {
  window.open('https://github.com/your-org/AutoCSR/blob/main/CHANGELOG.md', '_blank', 'noopener')
}

function onCommand(cmd: string): void {
  if (cmd === 'tour') openOnboarding()
  else if (cmd === 'shortcuts') openShortcuts()
  else if (cmd === 'docs') openDocs()
  else if (cmd === 'changelog') openChangelog()
}
</script>

<template>
  <el-dropdown trigger="click" @command="onCommand">
    <el-button text class="help-trigger" :aria-label="$t('help.menu_aria')">?</el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="shortcuts">⌨ {{ $t('help.shortcuts') }}</el-dropdown-item>
        <el-dropdown-item command="tour">🎬 {{ $t('help.tour') }}</el-dropdown-item>
        <el-dropdown-item command="docs">📖 {{ $t('help.docs') }}</el-dropdown-item>
        <el-dropdown-item command="changelog">📝 {{ $t('help.changelog') }}</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.help-trigger {
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-mute);
  width: 28px;
  height: 28px;
  border-radius: 50%;
}
.help-trigger:hover { background: var(--color-surface-3); color: var(--color-primary); }
</style>
