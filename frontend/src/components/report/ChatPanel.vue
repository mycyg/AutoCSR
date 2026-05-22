<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useChatStore } from '@/stores/chat'
import type { ChatMessageDTO, PatchDTO } from '@/api/rest'

const props = defineProps<{
  projectId: string
  nodeId: string | null
}>()

const emit = defineEmits<{
  (e: 'patch-applied'): void
  (e: 'rolled-back', version: number): void
}>()

const chatStore = useChatStore()
const input = ref('')
const scroller = ref<HTMLElement | null>(null)

const history = computed<ChatMessageDTO[]>(() =>
  (props.nodeId && chatStore.historyByNode[props.nodeId]) || [],
)

const thinking = computed(() => Boolean(props.nodeId && chatStore.thinking[props.nodeId]))

watch(() => props.nodeId, async (id) => {
  if (id) {
    await chatStore.loadHistory(props.projectId, id)
    await chatStore.loadVersions(props.projectId, id)
    await scrollToBottom()
  }
}, { immediate: true })

watch(history, () => { void scrollToBottom() })

async function scrollToBottom(): Promise<void> {
  await nextTick()
  const el = scroller.value
  if (el) el.scrollTop = el.scrollHeight
}

async function onSend(): Promise<void> {
  if (!props.nodeId || !input.value.trim() || thinking.value) return
  const msg = input.value.trim()
  input.value = ''
  try {
    const r = await chatStore.send(props.projectId, props.nodeId, msg)
    if (r.patches?.length) {
      emit('patch-applied')
      ElMessage.success(`已应用 ${r.patches.length} 处修改 (v${r.new_version})`)
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onRejectPatch(msg: ChatMessageDTO, _patch: PatchDTO): Promise<void> {
  // The patch is already applied to disk by the editor LLM. Rejecting means
  // rolling back to the version *before* this assistant turn ran.
  if (!props.nodeId) return
  const versions = chatStore.versionsByNode[props.nodeId] || []
  const turnVersion = Number(msg.meta?.new_version)
  if (!Number.isFinite(turnVersion)) {
    ElMessage.warning('该回复未关联版本，无法回滚')
    return
  }
  // Find the version immediately preceding this turn's snapshot
  const prior = versions.filter((v) => v < turnVersion).pop()
  if (!prior) {
    ElMessage.warning('找不到更早的版本，无法回滚')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将回滚到版本 v${prior}（撤销本次编辑）。继续？`,
      '拒绝补丁',
      { type: 'warning' },
    )
  } catch {
    return
  }
  await chatStore.rollback(props.projectId, props.nodeId, prior)
  emit('rolled-back', prior)
  ElMessage.success(`已回滚到 v${prior}`)
}

async function onDelete(msg: ChatMessageDTO): Promise<void> {
  if (!props.nodeId) return
  try {
    await ElMessageBox.confirm('删除这条对话记录？', '确认', { type: 'warning' })
  } catch { return }
  await chatStore.removeMessage(props.projectId, props.nodeId, msg.id)
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso
  }
}

function summarizePatch(p: PatchDTO): string {
  if (p.op === 'replace_section') return '整段替换'
  if (p.op === 'insert_paragraph') return `在第 ${p.target} 段后插入`
  if (p.op === 'replace_paragraph') return `替换第 ${p.target} 段`
  if (p.op === 'patch_field') return `局部替换 (${String(p.target).slice(0, 30)})`
  return p.op
}
</script>

<template>
  <div class="chat-panel">
    <div v-if="!nodeId" class="empty">
      ← 在左侧选择一个章节后开始对话编辑
    </div>
    <template v-else>
      <div class="messages" ref="scroller">
        <div v-if="history.length === 0" class="empty subtle">
          还没有对话。例如：「把第一段改得更正式一些」「检查 SAE 段落是否引用了 ADAE 数据」。
        </div>
        <div v-for="m in history" :key="m.id" class="bubble" :class="m.role">
          <div class="meta">
            <span class="role">{{ m.role === 'user' ? '我' : '助手' }}</span>
            <span class="ts">{{ fmtTime(m.ts) }}</span>
            <span v-if="m.meta?.new_version" class="ver">v{{ m.meta.new_version }}</span>
            <span class="spacer" />
            <el-button v-if="m.role !== 'system'" type="text" size="small"
                       @click="onDelete(m)">删除</el-button>
          </div>
          <div class="content">{{ m.content }}</div>
          <div v-if="m.patches?.length" class="patches">
            <div v-for="(p, i) in m.patches" :key="i" class="patch">
              <div class="patch-head">
                <el-tag size="small" type="success">{{ summarizePatch(p) }}</el-tag>
                <el-button v-if="m.role === 'assistant'" size="small" type="warning" plain
                           @click="onRejectPatch(m, p)">拒绝</el-button>
              </div>
              <div v-if="p.before" class="diff">
                <div class="col before">
                  <div class="col-title">改前</div>
                  <pre>{{ p.before }}</pre>
                </div>
                <div class="col after">
                  <div class="col-title">改后</div>
                  <pre>{{ p.after }}</pre>
                </div>
              </div>
              <div v-else class="diff single">
                <div class="col after">
                  <div class="col-title">新增</div>
                  <pre>{{ p.after }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div v-if="thinking" class="bubble assistant thinking">
          <span class="dot" />
          <span class="dot" />
          <span class="dot" />
        </div>
      </div>
      <div class="composer">
        <el-input v-model="input" type="textarea" :rows="2"
                  placeholder="说明你希望如何修改本节..."
                  :disabled="thinking"
                  @keydown.enter.exact.prevent="onSend"
                  @keydown.enter.shift.exact="" />
        <el-button type="primary" :disabled="thinking || !input.trim()" @click="onSend">
          {{ thinking ? '生成中…' : '发送 ⏎' }}
        </el-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.chat-panel { height: 100%; display: flex; flex-direction: column; }
.empty { padding: 40px 20px; text-align: center; color: #9ca3af; font-size: 13px; }
.empty.subtle { color: #b0b6be; font-size: 12px; }
.messages { flex: 1; overflow: auto; padding: 12px 8px; display: flex; flex-direction: column; gap: 10px; }
.bubble { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 8px 10px; }
.bubble.user { background: #eef4ff; border-color: #cfdfff; align-self: flex-end; max-width: 95%; }
.bubble.assistant { background: #fff; align-self: flex-start; max-width: 100%; }
.bubble.thinking { display: inline-flex; gap: 4px; padding: 10px 14px; }
.bubble.thinking .dot {
  width: 6px; height: 6px; border-radius: 50%; background: #9ca3af;
  animation: blink 1.2s infinite;
}
.bubble.thinking .dot:nth-child(2) { animation-delay: 0.2s; }
.bubble.thinking .dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink { 0%, 80%, 100% { opacity: 0.2; } 40% { opacity: 1; } }
.meta { display: flex; align-items: center; gap: 6px; font-size: 11px; color: #6b7280; margin-bottom: 4px; }
.meta .role { font-weight: 600; color: #374151; }
.meta .ver { background: #fef3c7; color: #92400e; padding: 1px 6px; border-radius: 999px; }
.meta .spacer { flex: 1; }
.content { white-space: pre-wrap; font-size: 13px; line-height: 1.55; color: #1f2937; }
.patches { margin-top: 8px; display: flex; flex-direction: column; gap: 6px; }
.patch { border: 1px dashed #cbd5e1; border-radius: 6px; padding: 6px 8px; background: #fafbfc; }
.patch-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.diff { display: flex; gap: 6px; }
.diff.single .col { flex: 1; }
.col { flex: 1; min-width: 0; }
.col-title { font-size: 10px; color: #6b7280; margin-bottom: 2px; }
.col pre { margin: 0; padding: 6px 8px; border-radius: 4px; font-size: 11px; max-height: 160px; overflow: auto; white-space: pre-wrap; word-break: break-word; }
.col.before pre { background: #fef2f2; color: #991b1b; border: 1px solid #fecaca; }
.col.after pre { background: #ecfdf5; color: #065f46; border: 1px solid #a7f3d0; }
.composer { padding: 8px; border-top: 1px solid #e5e7eb; display: flex; flex-direction: column; gap: 6px; }
.composer .el-button { align-self: flex-end; }
</style>
