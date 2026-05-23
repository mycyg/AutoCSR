<script setup lang="ts">
/**
 * Top-bar "?" help dropdown (M22 — v2.4).
 *
 * Adds two surfaces beyond the M18 dropdown:
 *   * Video tutorial — a placeholder card pointing at the project's
 *     YouTube/Bilibili demo channel.  The actual URLs are configured
 *     via runtime constants; see `docs/quickstart.md` § video script.
 *   * FAQ — 10 inline questions sourced from i18n `help.faq.*` keys
 *     so translators can keep them in lockstep.
 *
 * Each item dispatches via the global custom event bus so the relevant
 * modal (ShortcutsHelpModal / OnboardingTour) can pop up without
 * needing parent-child wiring.
 */
import { ref } from 'vue'
import { triggerShortcut } from '@/composables/useShortcuts'

const videoOpen = ref(false)
const faqOpen = ref(false)

// Placeholders — replace with real URLs once the 5-minute walkthrough
// video is recorded.  See docs/quickstart.md for the script.
const VIDEO_URLS = {
  youtube: 'https://www.youtube.com/results?search_query=AutoCSR+walkthrough',
  bilibili: 'https://search.bilibili.com/all?keyword=AutoCSR',
}

const FAQ_KEYS = [
  'q1', 'q2', 'q3', 'q4', 'q5',
  'q6', 'q7', 'q8', 'q9', 'q10',
] as const

function openOnboarding(): void {
  window.dispatchEvent(new CustomEvent('autocsr:onboarding:open'))
}
function openShortcuts(): void {
  triggerShortcut('help')
}
function openDocs(): void {
  window.open('https://github.com/your-org/AutoCSR/tree/main/docs', '_blank', 'noopener')
}
function openChangelog(): void {
  window.open('https://github.com/your-org/AutoCSR/blob/main/CHANGELOG.md', '_blank', 'noopener')
}

function onCommand(cmd: string): void {
  if (cmd === 'tour') openOnboarding()
  else if (cmd === 'shortcuts') openShortcuts()
  else if (cmd === 'docs') openDocs()
  else if (cmd === 'changelog') openChangelog()
  else if (cmd === 'video') videoOpen.value = true
  else if (cmd === 'faq') faqOpen.value = true
}
</script>

<template>
  <el-dropdown trigger="click" @command="onCommand">
    <el-button text class="help-trigger" :aria-label="$t('help.menu_aria')">?</el-button>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="shortcuts">⌨ {{ $t('help.shortcuts') }}</el-dropdown-item>
        <el-dropdown-item command="tour">🎬 {{ $t('help.tour') }}</el-dropdown-item>
        <el-dropdown-item command="video">▶ {{ $t('help.video') }}</el-dropdown-item>
        <el-dropdown-item command="faq">❓ {{ $t('help.faq_title') }}</el-dropdown-item>
        <el-dropdown-item divided command="docs">📖 {{ $t('help.docs') }}</el-dropdown-item>
        <el-dropdown-item command="changelog">📝 {{ $t('help.changelog') }}</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>

  <!-- Video tutorial modal -->
  <el-dialog v-model="videoOpen" :title="$t('help.video')" width="560" align-center>
    <p class="muted">{{ $t('help.video_desc') }}</p>
    <div class="video-placeholder" role="img" :aria-label="$t('help.video_placeholder_aria')">
      <span class="play" aria-hidden="true">▶</span>
      <span class="cap">{{ $t('help.video_placeholder') }}</span>
    </div>
    <ul class="video-links">
      <li>
        <a :href="VIDEO_URLS.youtube" target="_blank" rel="noopener">
          🔗 YouTube — {{ $t('help.video_search') }}
        </a>
      </li>
      <li>
        <a :href="VIDEO_URLS.bilibili" target="_blank" rel="noopener">
          🔗 Bilibili — {{ $t('help.video_search') }}
        </a>
      </li>
    </ul>
    <p class="muted small">{{ $t('help.video_script_note') }}</p>
    <template #footer>
      <el-button @click="videoOpen = false">{{ $t('common.close') }}</el-button>
    </template>
  </el-dialog>

  <!-- FAQ modal -->
  <el-dialog v-model="faqOpen" :title="$t('help.faq_title')" width="640" align-center>
    <el-collapse class="faq" accordion>
      <el-collapse-item v-for="k in FAQ_KEYS" :key="k" :name="k"
                         :title="$t(`help.faq.${k}.q`)">
        <p class="faq-a">{{ $t(`help.faq.${k}.a`) }}</p>
      </el-collapse-item>
    </el-collapse>
    <template #footer>
      <el-button @click="faqOpen = false">{{ $t('common.close') }}</el-button>
    </template>
  </el-dialog>
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
.muted { color: var(--color-text-mute); font-size: var(--font-size-md); }
.muted.small { font-size: var(--font-size-sm); }
.video-placeholder {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 28px 32px;
  background: var(--color-surface-2);
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-lg);
  margin: 14px 0;
  color: var(--color-text-mute);
}
.video-placeholder .play { font-size: 28px; }
.video-links {
  list-style: none;
  padding: 0;
  margin: 14px 0 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.video-links a {
  color: var(--color-primary);
  text-decoration: none;
}
.video-links a:hover { text-decoration: underline; }
.faq :deep(.el-collapse-item__header) {
  font-weight: 500;
  color: var(--color-text-strong);
}
.faq-a {
  margin: 4px 0;
  color: var(--color-text);
  line-height: 1.6;
}
</style>
