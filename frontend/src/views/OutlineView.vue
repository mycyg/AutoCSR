<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useOutlineStore } from '@/stores/outline'
import { connectProjectWS } from '@/api/ws'
import OutlineTree from '@/components/outline/OutlineTree.vue'
import NodeDetail from '@/components/outline/NodeDetail.vue'
import OutlineActions from '@/components/outline/OutlineActions.vue'
import EmptyState from '@/components/global/EmptyState.vue'
import { confirmAction } from '@/composables/useConfirm'
import { handleApiError } from '@/utils/errors'
const { t } = useI18n()

const props = defineProps<{ id: string }>()
const outlineStore = useOutlineStore()
const principleId = ref('ich_e3')
let wsClose: (() => void) | null = null

onMounted(async () => {
  try {
    await outlineStore.load(props.id)
    if (outlineStore.outline) {
      principleId.value = outlineStore.outline.principle_id
    }
  } catch {
    // No outline yet
  }
  wsClose = connectProjectWS(props.id, (ev) => {
    if (ev.type === 'outline.build_done' || ev.type === 'outline.restored') {
      void outlineStore.load(props.id)
    }
  })
})

onUnmounted(() => { wsClose?.(); outlineStore.reset() })

const selected = computed(() => outlineStore.findNode(outlineStore.selectedNodeId))

async function onBuild(): Promise<void> {
  if (outlineStore.outline) {
    if (!await confirmAction(
      t('outline.build'),
      { type: 'warning', confirm_text: 'common.confirm' },
    )) return
  }
  try {
    await outlineStore.build(props.id, principleId.value)
    ElMessage.success(`v${outlineStore.outline?.version ?? '?'}`)
  } catch (e) { handleApiError(e) }
}

async function onRestore(v: number): Promise<void> {
  if (!await confirmAction(`v${v}`, { type: 'warning' })) return
  try { await outlineStore.restore(props.id, v); ElMessage.success(`v${v}`) }
  catch (e) { handleApiError(e) }
}

async function onPatch(patch: Record<string, unknown>): Promise<void> {
  if (!selected.value) return
  try { await outlineStore.patchNode(props.id, selected.value.id, patch); ElMessage.success(t('common.ok')) }
  catch (e) { handleApiError(e) }
}

async function onAddChild(title: string, notes: string): Promise<void> {
  if (!selected.value) return
  try { await outlineStore.addChild(props.id, selected.value.id, title, notes); ElMessage.success(t('common.ok')) }
  catch (e) { handleApiError(e) }
}

async function onDelete(): Promise<void> {
  if (!selected.value) return
  if (!await confirmAction(t('common.delete'),
                            { type: 'warning', danger: true,
                              resource_name: selected.value.id })) return
  try { await outlineStore.removeNode(props.id, selected.value.id); ElMessage.success(t('common.ok')) }
  catch (e) { handleApiError(e) }
}
</script>

<template>
  <div class="outline-view">
    <el-container class="three">
      <el-aside class="left" width="380px">
        <EmptyState v-if="!outlineStore.outline"
                     icon="📋"
                     :title="$t('outline.empty_title')"
                     :description="$t('outline.empty_desc')">
          <el-select v-model="principleId" size="small" style="width: 180px; margin-top: 8px;">
            <el-option value="ich_e3" label="ICH E3" />
            <el-option value="cde_chem" label="CDE 化药" />
            <el-option value="cde_tcm" label="CDE 中药" />
          </el-select>
          <el-button type="primary" :loading="outlineStore.building"
                     style="margin-top: 12px;" @click="onBuild">
            {{ $t('outline.build') }}
          </el-button>
        </EmptyState>
        <OutlineTree v-else
          :nodes="outlineStore.outline.root_sections"
          :selected-id="outlineStore.selectedNodeId"
          @select="(id) => outlineStore.selectedNodeId = id" />
      </el-aside>

      <el-main class="center">
        <NodeDetail v-if="selected"
          :node="selected"
          :project-id="props.id"
          @patch="onPatch"
          @add-child="onAddChild"
          @delete="onDelete" />
        <div v-else-if="outlineStore.outline" class="empty-center">
          ← 在左侧选择一个节点查看 / 编辑
        </div>
      </el-main>

      <el-aside class="right" width="260px">
        <OutlineActions
          :outline="outlineStore.outline"
          :versions="outlineStore.versions"
          :building="outlineStore.building"
          @rebuild="onBuild"
          @restore="onRestore" />
      </el-aside>
    </el-container>
  </div>
</template>

<style scoped>
.outline-view {
  height: calc(100vh - 56px);
  display: flex; flex-direction: column;
}
.three { flex: 1; overflow: hidden; }
.left { background: var(--color-surface); border-right: 1px solid var(--color-border); overflow: auto; padding: 12px; }
.center { background: var(--color-surface-2); padding: 18px 24px; overflow: auto; }
.right { background: var(--color-surface); border-left: 1px solid var(--color-border); overflow: auto; padding: 12px; }
.empty { color: var(--color-text-mute); padding: 32px 12px; }
.empty p { margin-bottom: 10px; }
.empty-center { color: var(--color-text-faint); padding: 80px 0; text-align: center; }
@media (max-width: 1279px) {
  .left { width: 280px !important; }
  .right { width: 220px !important; }
}
@media (max-width: 1023px) {
  .three { flex-direction: column; }
  .left, .right { width: auto !important; border: none; border-bottom: 1px solid var(--color-border); max-height: 200px; }
}
</style>
