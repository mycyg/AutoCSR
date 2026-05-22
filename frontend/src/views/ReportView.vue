<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useOutlineStore } from '@/stores/outline'
import { useReportStore } from '@/stores/report'
import { connectProjectWS } from '@/api/ws'
import ChapterTree from '@/components/report/ChapterTree.vue'
import ChapterReader from '@/components/report/ChapterReader.vue'
import WriterStatus from '@/components/report/WriterStatus.vue'

const props = defineProps<{ id: string }>()
const outlineStore = useOutlineStore()
const reportStore = useReportStore()
let wsClose: (() => void) | null = null
let pollTimer: number | null = null

onMounted(async () => {
  try {
    await outlineStore.load(props.id)
  } catch {
    // No outline yet — user must build one first
  }
  await reportStore.refreshStatus(props.id)
  await reportStore.refreshDrafts(props.id)
  await reportStore.loadTerminology(props.id)
  wsClose = connectProjectWS(props.id, (ev) => reportStore.handleWS(props.id, ev))
  // Light fallback poll so the user gets updates even if WS is asleep
  pollTimer = window.setInterval(() => {
    if (reportStore.status?.current_phase === 'idle' || reportStore.status?.current_phase === 'done'
        || reportStore.status?.current_phase === 'error') return
    void reportStore.refreshStatus(props.id)
  }, 3000)
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
    ElMessage.warning('请先生成大纲')
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

const phase = computed(() => reportStore.phase)
const running = computed(() => ['background', 'results', 'discussion', 'harmonize'].includes(phase.value))
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
    <el-container class="three">
      <el-aside class="left" width="320px">
        <div v-if="!outlineStore.outline" class="empty">
          <p>项目尚无大纲，无法撰写。</p>
          <el-button size="small" plain @click="$router.push(`/p/${props.id}/outline`)">
            去生成大纲
          </el-button>
        </div>
        <ChapterTree v-else
          :nodes="outlineStore.outline.root_sections"
          :selected-id="reportStore.selectedNodeId"
          :drafts="draftsById"
          @select="onSelect" />
      </el-aside>

      <el-main class="center">
        <ChapterReader
          :project-id="props.id"
          :node-id="reportStore.selectedNodeId"
          :draft="reportStore.currentDraft"
          :outline-title="outlineNode?.title"
          @regenerate="(extra) => onRegenerate(extra)" />
      </el-main>

      <el-aside class="right" width="320px">
        <WriterStatus
          :status="reportStore.status"
          :terminology="reportStore.terminology"
          @save-terminology="onSaveTerminology" />
      </el-aside>
    </el-container>
  </div>
</template>

<style scoped>
.report-view { height: calc(100vh - 56px); display: flex; flex-direction: column; }
.topbar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; background: #fff; border-bottom: 1px solid #e5e7eb;
}
.topbar .info { color: #6b7280; font-size: 12px; }
.three { flex: 1; overflow: hidden; }
.left { background: #fff; border-right: 1px solid #e5e7eb; overflow: auto; padding: 12px; }
.center { background: #fafbfc; padding: 0; overflow: auto; }
.right { background: #fff; border-left: 1px solid #e5e7eb; overflow: auto; }
.empty { color: #6b7280; padding: 24px 12px; text-align: center; }
</style>
