<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useOutlineStore } from '@/stores/outline'
import { useReportStore } from '@/stores/report'
import { connectProjectWS } from '@/api/ws'
import ChapterTree from '@/components/report/ChapterTree.vue'
import ChapterReader from '@/components/report/ChapterReader.vue'
import WriterStatus from '@/components/report/WriterStatus.vue'
import EmptyState from '@/components/global/EmptyState.vue'
import { getHallucinationCheck } from '@/api/rest'
import { handleApiError } from '@/utils/errors'
import { useRecentlyViewed } from '@/composables/useRecentlyViewed'
import { useResponsive } from '@/composables/useResponsive'
import { useSwipe } from '@/composables/useTouchGestures'
import { normalizeNodeQuery, normalizeReportPanel } from '@/utils/deepLink'

const props = defineProps<{ id: string }>()
const route = useRoute()
const router = useRouter()
const { isMobile } = useResponsive()
const mobileTab = ref<'tree' | 'reader' | 'inspector'>('tree')
const readerWrap = ref<HTMLElement | null>(null)
const outlineStore = useOutlineStore()
const reportStore = useReportStore()
let wsClose: (() => void) | null = null
let pollTimer: number | null = null
const halluCounts = ref<Record<string, number>>({})
const recent = useRecentlyViewed(props.id)

const inspectorPanel = computed(() => {
  const panel = normalizeReportPanel(route.query.panel)
  return panel === 'reader' ? null : panel
})

const deepLinkHighlight = computed(() => {
  const raw = route.query.highlight
  return Array.isArray(raw) ? String(raw[0] || '') : String(raw || '')
})

async function refreshHallucinations(): Promise<void> {
  try {
    const r = await getHallucinationCheck(props.id)
    const counts: Record<string, number> = {}
    for (const f of r.findings || []) {
      counts[f.node_id] = (counts[f.node_id] || 0) + 1
    }
    halluCounts.value = counts
  } catch { /* no findings or endpoint unavailable */ }
}

function routeNodeId(): string {
  return normalizeNodeQuery(route.query as Record<string, unknown>)
}

async function applyRouteNode(): Promise<void> {
  const nodeId = routeNodeId()
  if (!nodeId || !outlineStore.outline) return
  await reportStore.selectNode(props.id, nodeId)
  if (isMobile.value) mobileTab.value = inspectorPanel.value ? 'inspector' : 'reader'
}

onMounted(async () => {
  try {
    await outlineStore.load(props.id)
  } catch {
    // No outline yet — user must build one first
  }
  await reportStore.refreshStatus(props.id)
  await reportStore.refreshDrafts(props.id)
  await reportStore.loadTerminology(props.id)
  await applyRouteNode()
  void refreshHallucinations()
  wsClose = connectProjectWS(props.id, (ev) => reportStore.handleWS(props.id, ev))
  // Light fallback poll so the user gets updates even if WS is asleep
  pollTimer = window.setInterval(() => {
    if (reportStore.status?.current_phase === 'idle' || reportStore.status?.current_phase === 'done'
        || reportStore.status?.current_phase === 'error') return
    void reportStore.refreshStatus(props.id)
  }, 3000)
})

watch(() => [route.query.node, route.query.node_id, route.query.panel, props.id], () => {
  void applyRouteNode()
})

onUnmounted(() => {
  wsClose?.()
  if (pollTimer !== null) window.clearInterval(pollTimer)
  reportStore.reset()
})

const draftsById = computed(() => {
  const m: Record<string, typeof reportStore.drafts[number]> = {}
  for (const d of reportStore.drafts) m[d.node_id] = d
  return m
})

const outlineNode = computed(() => outlineStore.findNode(reportStore.selectedNodeId))

async function onStart(): Promise<void> {
  if (!outlineStore.outline) {
    handleApiError(new Error('outline missing'))
    return
  }
  const leaves = (function count(nodes: typeof outlineStore.outline.root_sections): number {
    let n = 0
    for (const node of nodes) {
      if (!node.children?.length) n++
      else n += count(node.children)
    }
    return n
  })(outlineStore.outline.root_sections)
  const conf = await ElMessageBox.prompt(
    `将基于当前大纲并行生成 ${leaves} 节，writer 并发上限 4。` +
    `可输入"全部"或一个整数限制本次只写前 N 节。`,
    '开始撰写',
    {
      confirmButtonText: '开始',
      cancelButtonText: '取消',
      inputValue: '全部',
      inputPattern: /^(\d+|全部|all)$/i,
      inputErrorMessage: '请输入"全部"或数字',
    },
  ).catch(() => null)
  if (!conf) return
  let limit: number | undefined
  const raw = String(conf.value).trim()
  if (raw && raw !== '全部' && raw.toLowerCase() !== 'all') limit = parseInt(raw, 10)
  try {
    await reportStore.generate(props.id, true, limit)
    ElMessage.success('已开始撰写')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onSelect(id: string): Promise<void> {
  await reportStore.selectNode(props.id, id)
  const query: Record<string, any> = { ...route.query, node: id }
  delete query.node_id
  void router.replace({ path: route.path, query })
}

async function onRegenerate(extra?: string): Promise<void> {
  if (!reportStore.selectedNodeId) return
  try {
    await reportStore.regenerate(props.id, reportStore.selectedNodeId, extra)
    ElMessage.success('已重写本节')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onSaveTerminology(terms: Record<string, string>): Promise<void> {
  try {
    await reportStore.saveTerminology(props.id, terms)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onPatchApplied(): Promise<void> {
  if (!reportStore.selectedNodeId) return
  // Refresh the current draft so the center pane shows the edited markdown
  await reportStore.loadDraft(props.id, reportStore.selectedNodeId)
  await reportStore.refreshDrafts(props.id)
}

async function onRolledBack(_version: number): Promise<void> {
  if (!reportStore.selectedNodeId) return
  await reportStore.loadDraft(props.id, reportStore.selectedNodeId)
  await reportStore.refreshDrafts(props.id)
}

const phase = computed(() => reportStore.phase)
const running = computed(() => ['background', 'results', 'discussion', 'harmonize'].includes(phase.value))

// M22 — flat leaf order, used for swipe-left/right chapter navigation.
function flattenLeaves(nodes: Array<{ id: string; children?: any[] }>): string[] {
  const out: string[] = []
  for (const n of nodes) {
    if (!n.children?.length) out.push(n.id)
    else out.push(...flattenLeaves(n.children))
  }
  return out
}

const leafOrder = computed<string[]>(() => {
  if (!outlineStore.outline) return []
  return flattenLeaves(outlineStore.outline.root_sections as any)
})

function gotoOffset(delta: number): void {
  const order = leafOrder.value
  if (!order.length) return
  const cur = reportStore.selectedNodeId
  const idx = cur ? order.indexOf(cur) : -1
  const next = idx === -1 ? (delta > 0 ? 0 : order.length - 1)
                            : Math.max(0, Math.min(order.length - 1, idx + delta))
  if (order[next] && order[next] !== cur) void onSelect(order[next])
}

useSwipe(readerWrap, {
  onLeft: () => gotoOffset(+1),
  onRight: () => gotoOffset(-1),
})
</script>

<template>
  <div class="report-view">
    <div class="topbar">
      <el-button type="primary" :disabled="running || !outlineStore.outline"
                 @click="onStart">
        <span v-if="running">撰写中…</span>
        <span v-else>开始撰写</span>
      </el-button>
      <el-button v-if="running" disabled>
        <el-tooltip content="M5 支持中断" placement="bottom">
          <span>停止撰写</span>
        </el-tooltip>
      </el-button>
      <span class="info" v-if="reportStore.status">
        阶段 <b>{{ phase }}</b> ·
        {{ reportStore.leavesDone }} / {{ reportStore.leavesTotal }} ·
        tokens in {{ reportStore.totalTokens.input }} · out {{ reportStore.totalTokens.output }} ·
        {{ reportStore.totalWords }} 字
      </span>
    </div>
    <template v-if="isMobile">
      <el-tabs v-model="mobileTab" class="m-tabs">
        <el-tab-pane :label="$t('report.tab_tree')" name="tree" />
        <el-tab-pane :label="$t('report.tab_reader')" name="reader" />
        <el-tab-pane :label="$t('report.tab_inspector')" name="inspector" />
      </el-tabs>
      <div class="m-pane" ref="readerWrap">
        <template v-if="mobileTab === 'tree'">
          <EmptyState v-if="!outlineStore.outline"
                       icon="📋"
                       :title="$t('outline.empty_title')"
                       :description="$t('outline.empty_desc')"
                       :cta-text="$t('outline.build')"
                       @cta="$router.push(`/p/${props.id}/outline`)" />
          <ChapterTree v-else
            :nodes="outlineStore.outline.root_sections"
            :selected-id="reportStore.selectedNodeId"
            :drafts="draftsById"
            :hallucinations="halluCounts"
            @select="(id) => { onSelect(id); mobileTab = 'reader' }" />
        </template>
        <ChapterReader v-else-if="mobileTab === 'reader'"
          :project-id="props.id"
          :node-id="reportStore.selectedNodeId"
          :draft="reportStore.currentDraft"
          :outline-title="outlineNode?.title"
          :highlight="deepLinkHighlight"
          compact
          @regenerate="(extra) => onRegenerate(extra)" />
        <WriterStatus v-else
          :project-id="props.id"
          :node-id="reportStore.selectedNodeId"
          :outline-title="outlineNode?.title"
          :status="reportStore.status"
          :terminology="reportStore.terminology"
          :active-tab="inspectorPanel"
          @save-terminology="onSaveTerminology"
          @patch-applied="onPatchApplied"
          @rolled-back="onRolledBack"
          @refined="onPatchApplied"
          @comments-applied="onPatchApplied" />
      </div>
    </template>
    <el-container v-else class="three">
      <el-aside class="left" width="320px">
        <EmptyState v-if="!outlineStore.outline"
                     icon="📋"
                     :title="$t('outline.empty_title')"
                     :description="$t('outline.empty_desc')"
                     :cta-text="$t('outline.build')"
                     @cta="$router.push(`/p/${props.id}/outline`)" />
        <template v-else>
          <ChapterTree
            :nodes="outlineStore.outline.root_sections"
            :selected-id="reportStore.selectedNodeId"
            :drafts="draftsById"
            :hallucinations="halluCounts"
            @select="onSelect" />
          <div v-if="recent.items.value && recent.items.value.length" class="recent-list">
            <h4>★ {{ $t('report.recently_viewed') }}</h4>
            <ul>
              <li v-for="r in (recent.items.value || []).slice(0, 5)" :key="r.node_id">
                <button type="button" @click="onSelect(r.node_id)">
                <span class="rid">{{ r.node_id }}</span>
                <span class="rtitle">{{ r.title }}</span>
                </button>
              </li>
            </ul>
          </div>
        </template>
      </el-aside>

      <el-main class="center">
        <ChapterReader
          :project-id="props.id"
          :node-id="reportStore.selectedNodeId"
          :draft="reportStore.currentDraft"
          :outline-title="outlineNode?.title"
          :highlight="deepLinkHighlight"
          @regenerate="(extra) => onRegenerate(extra)" />
      </el-main>

      <el-aside class="right" width="420px">
        <WriterStatus
          :project-id="props.id"
          :node-id="reportStore.selectedNodeId"
          :outline-title="outlineNode?.title"
          :status="reportStore.status"
          :terminology="reportStore.terminology"
          :active-tab="inspectorPanel"
          @save-terminology="onSaveTerminology"
          @patch-applied="onPatchApplied"
          @rolled-back="onRolledBack"
          @refined="onPatchApplied"
          @comments-applied="onPatchApplied" />
      </el-aside>
    </el-container>
  </div>
</template>

<style scoped>
.report-view { height: calc(100vh - 56px); display: flex; flex-direction: column; }
.topbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; background: var(--color-surface); border-bottom: 1px solid var(--color-border);
}
.topbar .info { color: var(--color-text-mute); font-size: var(--font-size-sm); }
.three { flex: 1; overflow: hidden; }
.left { background: var(--color-surface); border-right: 1px solid var(--color-border); overflow: auto; padding: 12px; }
.center { background: var(--color-surface-2); padding: 0; overflow: auto; }
.right { background: var(--color-surface); border-left: 1px solid var(--color-border); overflow: auto; }
.empty { color: var(--color-text-mute); padding: 24px 12px; text-align: center; }
.recent-list { margin-top: 12px; padding: 8px 4px; border-top: 1px solid var(--color-border); }
.recent-list h4 {
  margin: 0 0 6px; font-size: var(--font-size-sm);
  color: var(--color-text-mute); font-weight: 600;
}
.recent-list ul { list-style: none; margin: 0; padding: 0; }
.recent-list li { margin: 0; }
.recent-list button {
  width: 100%;
  min-height: 32px;
  padding: 4px 6px;
  cursor: pointer;
  border-radius: 4px;
  border: 0;
  background: transparent;
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: var(--font-size-sm);
  text-align: left;
}
.recent-list button:hover { background: var(--color-surface-3); }
.recent-list .rid { font-family: ui-monospace, monospace; color: var(--color-text-mute); font-size: var(--font-size-xs); min-width: 40px; }
.recent-list .rtitle { color: var(--color-text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 1279px) {
  .left { width: 260px !important; }
  .right { width: 320px !important; }
}
@media (max-width: 1023px) {
  .three { flex-direction: column; }
  .left, .right { width: auto !important; max-height: 220px; border: none; border-bottom: 1px solid var(--color-border); }
}
@media (max-width: 767px) {
  .report-view { height: calc(100dvh - 48px); }
  .topbar { padding: 6px 10px; }
  .topbar .info { display: none; }
}
.m-tabs { background: var(--color-surface); border-bottom: 1px solid var(--color-border); }
.m-tabs :deep(.el-tabs__header) { margin: 0; }
.m-pane { flex: 1; overflow: auto; background: var(--color-surface-2); touch-action: pan-y; }
</style>
