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
import TaskBadge from '@/components/global/TaskBadge.vue'
import { getBlinding, getLock } from '@/api/rest'
import { onMounted, ref, watch } from 'vue'

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
  { key: 'audit', i18nKey: 'steps.audit', path: 'audit' },
]

const blinded = ref(false)
const locked = ref(false)

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
  if (n === 'project-detail') return 'intake'
  return ''
})

function go(step: typeof steps[number]): void {
  if (!projectId.value) return
  router.push(`/p/${projectId.value}/${step.path}`)
}
</script>

<template>
  <el-container class="autocsr-shell" direction="vertical">
    <el-header class="autocsr-header">
      <div class="brand" @click="router.push('/')">{{ $t('app.title') }} · {{ projectName }}</div>
      <StepNavigator :steps="steps" :project-id="projectId" :active-key="activeKey" @go="go" />
      <div class="actions">
        <el-tag v-if="blinded" type="primary" size="small">● 盲态</el-tag>
        <el-tag v-if="locked" type="warning" size="small">● 数据已锁定</el-tag>
        <TaskBadge v-if="projectId" :project-id="projectId" />
        <UserSwitch />
        <LanguageSwitch />
        <el-tag size="small" type="success">V2-F</el-tag>
      </div>
    </el-header>
    <GlobalAlertBar v-if="projectId" :project-id="projectId" />
    <PIIWarningBanner v-if="projectId" :project-id="projectId" />
    <el-main class="autocsr-main">
      <router-view />
    </el-main>
    <ShortcutsHelpModal />
    <GlobalSearchModal />
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
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  height: 56px;
}
.brand {
  font-weight: 600;
  font-size: 16px;
  color: #1f2937;
  cursor: pointer;
}
.actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.autocsr-main {
  padding: 0;
  background: #f5f7fa;
  overflow: hidden;
}
</style>
