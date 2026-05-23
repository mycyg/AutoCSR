<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import GlobalAlertBar from '@/components/global/GlobalAlertBar.vue'
import LanguageSwitch from '@/components/global/LanguageSwitch.vue'
import StepNavigator from '@/components/global/StepNavigator.vue'
import ShortcutsHelpModal from '@/components/global/ShortcutsHelpModal.vue'
import GlobalSearchModal from '@/components/global/GlobalSearchModal.vue'
import PIIWarningBanner from '@/components/global/PIIWarningBanner.vue'
import UserSwitch from '@/components/global/UserSwitch.vue'
import UserAvatar from '@/components/global/UserAvatar.vue'
import TaskBadge from '@/components/global/TaskBadge.vue'
import { useAuthStore } from '@/stores/auth'
import TaskProgressOverlay from '@/components/global/TaskProgressOverlay.vue'
import OnboardingTour from '@/components/global/OnboardingTour.vue'
import HelpMenu from '@/components/global/HelpMenu.vue'
import ThemeToggle from '@/components/global/ThemeToggle.vue'
import { getBlinding, getLock } from '@/api/rest'
import { onMounted, ref, watch } from 'vue'
import { Menu } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const projectId = computed(() => (route.params.id as string | undefined) || '')
const projectName = computed(() => (
  projectId.value
    ? `${t('app.project_prefix')} ${projectId.value.slice(0, 8)}`
    : t('app.title')
))

const steps = [
  { key: 'intake', i18nKey: 'steps.intake', path: 'intake' },
  { key: 'cleanse', i18nKey: 'steps.cleanse', path: 'cleanse' },
  { key: 'analyze', i18nKey: 'steps.analyze', path: 'analyze' },
  { key: 'outline', i18nKey: 'steps.outline', path: 'outline' },
  { key: 'report', i18nKey: 'steps.report', path: 'report' },
  { key: 'review', i18nKey: 'steps.review', path: 'review' },
  { key: 'tasks', i18nKey: 'steps.tasks', path: 'tasks' },
  { key: 'export', i18nKey: 'steps.export', path: 'export' },
  { key: 'dashboard', i18nKey: 'steps.dashboard', path: 'dashboard' },
  { key: 'audit', i18nKey: 'steps.audit', path: 'audit' },
]

const blinded = ref(false)
const locked = ref(false)
const stepDropdownOpen = ref(false)

async function refreshChips(): Promise<void> {
  if (!projectId.value) {
    blinded.value = false
    locked.value = false
    return
  }
  try {
    const [bl, lk] = await Promise.all([
      getBlinding(projectId.value),
      getLock(projectId.value),
    ])
    blinded.value = !!bl.blinded
    locked.value = !!lk.locked
  } catch {
    blinded.value = false
    locked.value = false
  }
}
onMounted(refreshChips)
watch(projectId, refreshChips)

// M21 — hydrate the JWT-resolved user (if any) on first paint so
// UserAvatar shows the real account, not the dev fallback.
const auth = useAuthStore()
onMounted(() => { auth.fetchMe() })

const activeKey = computed(() => {
  const n = String(route.name || '')
  if (n.includes('intake')) return 'intake'
  if (n.includes('cleanse')) return 'cleanse'
  if (n.includes('analyze')) return 'analyze'
  if (n.includes('outline')) return 'outline'
  if (n.includes('review')) return 'review'
  if (n.includes('report')) return 'report'
  if (n.includes('audit')) return 'audit'
  if (n.includes('tasks')) return 'tasks'
  if (n.includes('export')) return 'export'
  if (n === 'project-detail') return 'dashboard'
  return ''
})

function go(step: typeof steps[number]): void {
  if (!projectId.value) return
  router.push(`/p/${projectId.value}/${step.path}`)
  stepDropdownOpen.value = false
}

function goCommand(key: string): void {
  const step = steps.find(s => s.key === key)
  if (step) go(step)
}
</script>

<template>
  <el-container class="autocsr-shell" direction="vertical">
    <a href="#main-content" class="skip-link">{{ $t('a11y.skip_to_content') }}</a>
    <el-header class="autocsr-header" role="banner">
      <button type="button" class="brand"
            @click="router.push('/')"
            :aria-label="$t('app.title')">{{ $t('app.title') }} · {{ projectName }}</button>
      <!-- Desktop step navigator -->
      <div class="step-nav-desktop">
        <StepNavigator :steps="steps" :project-id="projectId" :active-key="activeKey" @go="go" />
      </div>
      <!-- Mobile / tablet dropdown -->
      <div class="step-nav-mobile">
        <el-dropdown trigger="click" @command="goCommand">
          <el-button text :icon="Menu" :aria-label="$t('steps.intake')" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-for="s in steps" :key="s.key" :command="s.key"
                                 :disabled="!projectId">
                {{ $t(s.i18nKey) }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="actions">
        <el-tag v-if="blinded" type="primary" size="small">● {{ $t('common.status') }}</el-tag>
        <el-tag v-if="locked" type="warning" size="small">●</el-tag>
        <TaskBadge v-if="projectId" :project-id="projectId" />
        <UserSwitch v-if="!auth.isAuthenticated" />
        <UserAvatar v-else />
        <LanguageSwitch />
        <ThemeToggle />
        <HelpMenu />
        <el-tag size="small" type="success">v1.0</el-tag>
      </div>
    </el-header>
    <GlobalAlertBar v-if="projectId" :project-id="projectId" />
    <PIIWarningBanner v-if="projectId" :project-id="projectId" />
    <el-main id="main-content" class="autocsr-main" role="main">
      <router-view />
    </el-main>
    <ShortcutsHelpModal />
    <GlobalSearchModal />
    <TaskProgressOverlay />
    <OnboardingTour />
  </el-container>
</template>

<style scoped>
.autocsr-shell {
  height: 100vh;
}
.autocsr-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0 24px;
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  height: 56px;
  overflow: hidden;
}
.brand {
  flex: 0 1 240px;
  min-width: 120px;
  font-weight: 600;
  font-size: var(--font-size-xl);
  color: var(--color-text-strong);
  cursor: pointer;
  border: 0;
  background: transparent;
  padding: 0;
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.step-nav-desktop {
  flex: 1 1 auto;
  min-width: 0;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
}
.step-nav-desktop::-webkit-scrollbar {
  display: none;
}
.actions {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.autocsr-main {
  padding: 0;
  background: var(--color-bg);
  overflow: hidden;
}
.step-nav-mobile { display: none; }
@media (max-width: 1023px) {
  .step-nav-desktop { display: none; }
  .step-nav-mobile { display: inline-flex; }
  .autocsr-header { padding: 0 12px; }
  .actions > :nth-child(n+4) {
    /* hide non-essential chips on small screens */
    display: none;
  }
}
@media (max-width: 767px) {
  /* M22 — mobile: sticky shrunken header, tighter spacing, smaller brand. */
  .autocsr-shell { height: 100dvh; }
  .autocsr-header {
    position: sticky;
    top: 0;
    z-index: 30;
    padding: 0 8px;
    height: 48px;
  }
  .brand {
    font-size: var(--font-size-md);
    max-width: 50%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .actions { gap: 4px; }
  .actions > :nth-child(n+2) { display: none; }
}

/* Skip-to-content link (WCAG 2.4.1). Hidden until focused. */
.skip-link {
  position: absolute;
  top: -100px;
  left: 8px;
  z-index: 100;
  background: var(--color-primary);
  color: #fff;
  padding: 8px 14px;
  border-radius: 0 0 var(--radius-md) var(--radius-md);
  text-decoration: none;
  font-weight: 600;
  font-size: var(--font-size-md);
  transition: top 120ms ease;
}
.skip-link:focus,
.skip-link:focus-visible {
  top: 0;
  outline: 2px solid #fff;
  outline-offset: -4px;
}
</style>
