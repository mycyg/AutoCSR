<script setup lang="ts">
/**
 * First-visit onboarding tour.
 *
 * Pure Vue / Element Plus (no intro.js dependency) — a centred modal
 * stepping through 6 narrative steps with skip + "don't show again".
 *
 * Visibility persists in localStorage:
 *   - autocsr_onboarding_done  → never auto-open again
 *   - autocsr_onboarding_seen  → user hit skip / close
 *
 * Other code can call `triggerOnboarding()` to manually relaunch.
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

const { t } = useI18n()
const route = useRoute()
const visible = ref(false)
const step = ref(0)
const dontShow = ref(false)

interface Step {
  title: string
  body: string
  icon: string
}

const steps: Step[] = [
  { icon: '👋', title: 'onboarding.s1_title', body: 'onboarding.s1_body' },
  { icon: '🧪', title: 'onboarding.s_demo_title', body: 'onboarding.s_demo_body' },
  { icon: '📤', title: 'onboarding.s2_title', body: 'onboarding.s2_body' },
  { icon: '🧹', title: 'onboarding.s3_title', body: 'onboarding.s3_body' },
  { icon: '✍️', title: 'onboarding.s4_title', body: 'onboarding.s4_body' },
  { icon: '📦', title: 'onboarding.s5_title', body: 'onboarding.s5_body' },
  { icon: '🎉', title: 'onboarding.s6_title', body: 'onboarding.s6_body' },
]

function open(): void {
  step.value = 0
  dontShow.value = false
  visible.value = true
}

function close(): void {
  visible.value = false
  try {
    window.localStorage.setItem('autocsr_onboarding_seen', '1')
    if (dontShow.value) {
      window.localStorage.setItem('autocsr_onboarding_done', '1')
    }
  } catch { /* ignore */ }
}

function next(): void {
  if (step.value < steps.length - 1) step.value += 1
  else close()
}

function prev(): void {
  if (step.value > 0) step.value -= 1
}

function maybeAutoOpen(): void {
  // Defer so router transitions settle.
  window.setTimeout(() => {
    try {
      if (window.localStorage.getItem('autocsr_onboarding_done') === '1') return
      if (window.localStorage.getItem('autocsr_onboarding_seen') === '1') return
    } catch { return }
    if (route.path.startsWith('/p/')) return
    open()
  }, 600)
}

onMounted(() => {
  maybeAutoOpen()
  window.addEventListener('autocsr:onboarding:open', open)
})

onUnmounted(() => {
  window.removeEventListener('autocsr:onboarding:open', open)
})

// Public hook so the help menu / re-launch link can pop it open.
defineExpose({ open })

</script>

<template>
  <el-dialog v-model="visible" :show-close="true" :close-on-click-modal="false"
              :close-on-press-escape="true" width="480" align-center
              :aria-label="t('onboarding.aria')"
              class="onboarding-tour">
    <div class="step">
      <div class="icon" aria-hidden="true">{{ steps[step].icon }}</div>
      <h2 class="title">{{ t(steps[step].title) }}</h2>
      <p class="body">{{ t(steps[step].body) }}</p>
      <div class="dots" :aria-label="t('onboarding.progress', { n: step + 1, total: steps.length })">
        <span v-for="(_, i) in steps" :key="i" class="dot" :class="{ active: i === step }" />
      </div>
    </div>
    <template #footer>
      <div class="actions">
        <el-checkbox v-model="dontShow">{{ t('onboarding.dont_show') }}</el-checkbox>
        <span class="spacer" />
        <el-button text @click="close">{{ t('onboarding.skip') }}</el-button>
        <el-button v-if="step > 0" plain @click="prev">{{ t('onboarding.prev') }}</el-button>
        <el-button type="primary" @click="next">
          {{ step === steps.length - 1 ? t('onboarding.finish') : t('onboarding.next') }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.step {
  text-align: center;
  padding: 8px 4px 12px;
}
.step .icon {
  font-size: 56px;
  margin-bottom: 8px;
  line-height: 1;
}
.step .title {
  margin: 0 0 12px 0;
  font-size: var(--font-size-2xl);
  color: var(--color-text-strong);
}
.step .body {
  margin: 0 auto;
  max-width: 360px;
  color: var(--color-text-mute);
  line-height: 1.6;
  font-size: var(--font-size-md);
}
.dots {
  display: flex;
  justify-content: center;
  gap: 6px;
  margin-top: 18px;
}
.dot {
  width: 7px; height: 7px;
  border-radius: 50%;
  background: var(--color-border-strong);
  transition: background 180ms ease;
}
.dot.active { background: var(--color-primary); }
.actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.actions .spacer { flex: 1; }
</style>
