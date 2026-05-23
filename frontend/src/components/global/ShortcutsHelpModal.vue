<script setup lang="ts">
import { ref } from 'vue'
import { useShortcuts } from '@/composables/useShortcuts'

const visible = ref(false)
const tab = ref<'keys' | 'workflows'>('keys')

useShortcuts({
  help: () => { visible.value = true; tab.value = 'keys' },
  show_view_shortcuts: () => { visible.value = true; tab.value = 'keys' },
})

const isMac = typeof navigator !== 'undefined' &&
  /Mac|iPhone|iPod|iPad/i.test(navigator.platform || '')
const mod = isMac ? '⌘' : 'Ctrl'
</script>

<template>
  <el-dialog v-model="visible" :title="$t('shortcuts.title')" width="540" align-center>
    <el-tabs v-model="tab">
      <el-tab-pane :label="$t('shortcuts.tab_keys')" name="keys">
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
              <td><kbd>{{ mod }}</kbd> + <kbd>/</kbd></td>
              <td>{{ $t('shortcuts.view_shortcuts') }}</td>
            </tr>
            <tr>
              <td><kbd>?</kbd></td>
              <td>{{ $t('shortcuts.help') }}</td>
            </tr>
            <tr>
              <td><kbd>j</kbd> / <kbd>k</kbd></td>
              <td>{{ $t('shortcuts.outline_nav') }}</td>
            </tr>
            <tr>
              <td><kbd>↑</kbd> / <kbd>↓</kbd></td>
              <td>{{ $t('shortcuts.list_nav') }}</td>
            </tr>
            <tr>
              <td><kbd>Esc</kbd></td>
              <td>{{ $t('shortcuts.close_modal') }}</td>
            </tr>
            <tr>
              <td><kbd>Shift</kbd> + <kbd>Enter</kbd></td>
              <td>{{ $t('shortcuts.send_message') }}</td>
            </tr>
          </tbody>
        </table>
      </el-tab-pane>
      <el-tab-pane :label="$t('shortcuts.tab_workflows')" name="workflows">
        <div class="workflow">
          <h4>✍ {{ $t('shortcuts.workflows.writing') }}</h4>
          <div class="steps">{{ $t('shortcuts.workflows.writing_steps') }}</div>
        </div>
        <div class="workflow">
          <h4>🔍 {{ $t('shortcuts.workflows.review') }}</h4>
          <div class="steps">{{ $t('shortcuts.workflows.review_steps') }}</div>
        </div>
        <div class="workflow">
          <h4>❓ {{ $t('shortcuts.workflows.data_ask') }}</h4>
          <div class="steps">{{ $t('shortcuts.workflows.data_ask_steps') }}</div>
        </div>
        <div class="workflow">
          <h4>📦 {{ $t('shortcuts.workflows.export') }}</h4>
          <div class="steps">{{ $t('shortcuts.workflows.export_steps') }}</div>
        </div>
      </el-tab-pane>
    </el-tabs>
  </el-dialog>
</template>

<style scoped>
.grid { width: 100%; border-collapse: collapse; }
.grid td {
  padding: 8px 6px;
  border-bottom: 1px solid var(--color-border);
  color: var(--color-text);
  font-size: var(--font-size-md);
}
.grid td:first-child { width: 40%; }
kbd {
  display: inline-block;
  background: var(--color-surface-3);
  border: 1px solid var(--color-border-strong);
  border-bottom-width: 2px;
  border-radius: 4px;
  padding: 1px 6px;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: var(--font-size-sm);
  color: var(--color-text-strong);
}
.workflow {
  padding: 12px 6px;
  border-bottom: 1px solid var(--color-border);
}
.workflow:last-child { border-bottom: none; }
.workflow h4 {
  margin: 0 0 6px 0;
  font-size: var(--font-size-md);
  color: var(--color-text-strong);
  font-weight: 600;
}
.steps {
  font-size: var(--font-size-sm);
  color: var(--color-text-mute);
  font-family: ui-monospace, monospace;
}
</style>
