<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import LeftPanel from '@/components/LeftPanel.vue'
import CenterEditor from '@/components/CenterEditor.vue'
import RightPanel from '@/components/RightPanel.vue'
import ProjectMembersDialog from '@/components/global/ProjectMembersDialog.vue'
import { useProjectStore } from '@/stores/project'
import { useResponsive } from '@/composables/useResponsive'
import { useAuthStore } from '@/stores/auth'
import { useI18n } from 'vue-i18n'
import { listProjectMembers } from '@/api/rest'

const props = defineProps<{ id: string }>()
const store = useProjectStore()
const auth = useAuthStore()
const { isMobile } = useResponsive()
const { t } = useI18n()

const mobileTab = ref<'outline' | 'editor' | 'inspector'>('editor')
const membersOpen = ref(false)
const canManageMembers = ref(false)

async function refreshMemberCap(): Promise<void> {
  // Only owners (or admins) should see the "permissions" entry.
  canManageMembers.value = false
  if (!auth.isAuthenticated && !auth.user) {
    // Dev mode without auth — hide the button rather than risk a stray 403.
    return
  }
  try {
    const members = await listProjectMembers(props.id)
    const me = auth.user?.id
    canManageMembers.value = !!members.find(m => m.user_id === me && m.role === 'owner')
              || auth.isAdmin
  } catch {
    canManageMembers.value = false
  }
}

onMounted(async () => {
  await store.load(props.id)
  void refreshMemberCap()
})
watch(() => props.id, async (id) => {
  await store.load(id)
  void refreshMemberCap()
})
</script>

<template>
  <div class="detail-root">
    <!-- M21 leftover — top-bar entry for project members (owner only). -->
    <div v-if="canManageMembers" class="detail-actions" role="toolbar"
          :aria-label="t('members.toolbar_aria')">
      <el-button size="small" plain @click="membersOpen = true"
                  :aria-label="t('members.open')">
        👥 {{ t('members.title') }}
      </el-button>
    </div>

    <!-- Mobile: tab strip + single-pane content. -->
    <template v-if="isMobile">
      <el-tabs v-model="mobileTab" class="m-tabs" :aria-label="t('detail.m_tabs_aria')">
        <el-tab-pane :label="t('detail.tab_outline')" name="outline" />
        <el-tab-pane :label="t('detail.tab_editor')" name="editor" />
        <el-tab-pane :label="t('detail.tab_inspector')" name="inspector" />
      </el-tabs>
      <div class="m-pane">
        <LeftPanel v-if="mobileTab === 'outline'" :project-id="props.id" />
        <CenterEditor v-else-if="mobileTab === 'editor'" :project-id="props.id" />
        <RightPanel v-else :project-id="props.id" />
      </div>
    </template>

    <!-- Tablet + desktop: three-pane layout (existing behaviour). -->
    <el-container v-else class="detail">
      <el-aside class="left" width="280px">
        <LeftPanel :project-id="props.id" />
      </el-aside>
      <el-main class="center">
        <CenterEditor :project-id="props.id" />
      </el-main>
      <el-aside class="right" width="360px">
        <RightPanel :project-id="props.id" />
      </el-aside>
    </el-container>

    <ProjectMembersDialog v-model="membersOpen" :project-id="props.id" />
  </div>
</template>

<style scoped>
.detail-root {
  height: 100%;
  display: flex;
  flex-direction: column;
  position: relative;
}
.detail-actions {
  position: absolute;
  top: 8px;
  right: 12px;
  z-index: 5;
}
.detail {
  height: 100%;
}
.left {
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  overflow: auto;
}
.center {
  padding: 0;
  background: var(--color-surface-2);
  overflow: auto;
}
.right {
  background: var(--color-surface);
  border-left: 1px solid var(--color-border);
  overflow: auto;
}
@media (max-width: 1279px) {
  .left { width: 220px !important; }
  .right { width: 300px !important; }
}
@media (max-width: 1023px) {
  .detail { flex-direction: column; }
  .left, .right { width: auto !important; max-height: 200px; border: none; border-bottom: 1px solid var(--color-border); }
}
.m-tabs {
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}
.m-tabs :deep(.el-tabs__nav-wrap) { padding: 0 8px; }
.m-tabs :deep(.el-tabs__header) { margin: 0; }
.m-pane {
  flex: 1;
  overflow: auto;
  background: var(--color-surface-2);
  font-size: var(--font-size-lg);
}
@media (max-width: 767px) {
  .detail-actions { top: 4px; right: 6px; }
}
</style>
