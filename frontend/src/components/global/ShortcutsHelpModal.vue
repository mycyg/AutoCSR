<script setup lang="ts">
import { ref } from 'vue'
import { useShortcuts } from '@/composables/useShortcuts'

const visible = ref(false)

useShortcuts({ help: () => { visible.value = true } })

const isMac = typeof navigator !== 'undefined' &&
  /Mac|iPhone|iPod|iPad/i.test(navigator.platform || '')
const mod = isMac ? '⌘' : 'Ctrl'
</script>

<template>
  <el-dialog v-model="visible" :title="$t('shortcuts.title')" width="420" align-center>
    <table class="grid">
      <tbody>
        <tr>
          <td><kbd>{{ mod }}</kbd> + <kbd>S</kbd></td>
          <td>{{ $t('shortcuts.save_section') }}</td>
        </tr>
        <tr>
          <td><kbd>{{ mod }}</kbd> + <kbd>K</kbd></td>
          <td>{{ $t('shortcuts.global_search') }}</td>
        </tr>
        <tr>
          <td><kbd>Shift</kbd> + <kbd>Enter</kbd></td>
          <td>{{ $t('shortcuts.send_message') }}</td>
        </tr>
        <tr>
          <td><kbd>?</kbd></td>
          <td>{{ $t('shortcuts.help') }}</td>
        </tr>
      </tbody>
    </table>
  </el-dialog>
</template>

<style scoped>
.grid { width: 100%; border-collapse: collapse; }
.grid td { padding: 8px 6px; border-bottom: 1px solid #f0f1f4; color: #374151; font-size: 13px; }
.grid td:first-child { width: 40%; }
kbd {
  display: inline-block;
  background: #f3f4f6;
  border: 1px solid #d1d5db;
  border-bottom-width: 2px;
  border-radius: 4px;
  padding: 1px 6px;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 12px;
  color: #1f2937;
}
</style>
