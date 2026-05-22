<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useOutlineStore } from '@/stores/outline'
import { connectProjectWS } from '@/api/ws'
import OutlineTree from '@/components/outline/OutlineTree.vue'
import NodeDetail from '@/components/outline/NodeDetail.vue'
import OutlineActions from '@/components/outline/OutlineActions.vue'

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
  try {
    if (outlineStore.outline) {
      await ElMessageBox.confirm(
        '重新生成会创建一个新的 outline 版本，旧版本会归档到 outline_v{N}.json，可随时回滚。',
        '重新生成大纲',
        { type: 'warning' },
      )
    }
    await outlineStore.build(props.id, principleId.value)
    ElMessage.success(`大纲已生成 v${outlineStore.outline?.version ?? '?'}`)
  } catch (e) {
    if (e instanceof Error && e.message.includes('cancel')) return
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onRestore(v: number): Promise<void> {
  try {
    await outlineStore.restore(props.id, v)
    ElMessage.success(`已回滚到 v${v}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onPatch(patch: Record<string, unknown>): Promise<void> {
  if (!selected.value) return
  try {
    await outlineStore.patchNode(props.id, selected.value.id, patch)
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onAddChild(title: string, notes: string): Promise<void> {
  if (!selected.value) return
  await outlineStore.addChild(props.id, selected.value.id, title, notes)
  ElMessage.success('已新增子节')
}

async function onDelete(): Promise<void> {
  if (!selected.value) return
  await ElMessageBox.confirm(`确定删除节点 ${selected.value.id} 及其所有子节？`, '删除节点',
    { type: 'warning' })
  await outlineStore.removeNode(props.id, selected.value.id)
  ElMessage.success('已删除')
}
</script>

<template>
  <div class="outline-view">
    <el-container class="three">
      <el-aside class="left" width="380px">
        <div v-if="!outlineStore.outline" class="empty">
          <p>项目尚无大纲。</p>
          <el-select v-model="principleId" size="small" style="width: 180px; margin-bottom: 8px">
            <el-option value="ich_e3" label="ICH E3" />
            <el-option value="cde_chem" label="CDE 化药" />
            <el-option value="cde_tcm" label="CDE 中药" />
          </el-select>
          <br />
          <el-button type="primary" :loading="outlineStore.building" @click="onBuild">
            生成大纲
          </el-button>
        </div>
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
.left { background: #fff; border-right: 1px solid #e5e7eb; overflow: auto; padding: 12px; }
.center { background: #fafbfc; padding: 18px 24px; overflow: auto; }
.right { background: #fff; border-left: 1px solid #e5e7eb; overflow: auto; padding: 12px; }
.empty { color: #6b7280; padding: 32px 12px; }
.empty p { margin-bottom: 10px; }
.empty-center { color: #9ca3af; padding: 80px 0; text-align: center; }
</style>
