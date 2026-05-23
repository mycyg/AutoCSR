<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  addComment, applyComments, deleteComment, listComments, patchComment,
  type CommentDTO,
} from '@/api/rest'

const props = defineProps<{
  projectId: string
  nodeId: string | null
}>()

const emit = defineEmits<{
  (e: 'applied'): void
}>()

const comments = ref<CommentDTO[]>([])
const draftBody = ref('')
const applying = ref(false)

async function refresh(): Promise<void> {
  if (!props.nodeId) {
    comments.value = []
    return
  }
  try {
    comments.value = await listComments(props.projectId, { node_id: props.nodeId })
  } catch {
    comments.value = []
  }
}

watch(() => props.nodeId, () => { void refresh() }, { immediate: true })

const grouped = computed(() => {
  const out: Record<string, CommentDTO[]> = { open: [], resolved: [], rejected: [] }
  for (const c of comments.value) out[c.status]?.push(c)
  return out
})

const openCount = computed(() => grouped.value.open.length)

async function onAdd(): Promise<void> {
  if (!props.nodeId) return
  const text = draftBody.value.trim()
  if (!text) {
    ElMessage.warning('批注内容不能为空')
    return
  }
  try {
    await addComment(props.projectId, props.nodeId, 0, [0, 0], text)
    draftBody.value = ''
    await refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onPatch(c: CommentDTO, status: 'open' | 'resolved' | 'rejected'): Promise<void> {
  try {
    await patchComment(props.projectId, c.id, { status })
    await refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onDelete(c: CommentDTO): Promise<void> {
  try {
    await deleteComment(props.projectId, c.id)
    await refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onApplyAll(): Promise<void> {
  if (!openCount.value) return
  const ok = await ElMessageBox.confirm(
    `将把 ${openCount.value} 条未解决批注一次性喂给 editor_llm 自动改稿，` +
    `生成新的 draft 版本（可在 diff 视图回查）。继续？`,
    '批量应用',
    { type: 'warning' },
  ).then(() => true).catch(() => false)
  if (!ok) return
  applying.value = true
  try {
    const res = await applyComments(props.projectId)
    ElMessage.success(
      `已应用 ${res.applied_count} 个补丁，跳过 ${res.skipped_count}；` +
      `新版本 ${Object.entries(res.new_versions).map(([k, v]) => `${k}→v${v}`).join(', ') || '无'}`,
    )
    await refresh()
    emit('applied')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    applying.value = false
  }
}
</script>

<template>
  <div class="comments-panel">
    <div v-if="!nodeId" class="empty">请先选择章节</div>
    <template v-else>
      <div class="composer">
        <el-input v-model="draftBody" type="textarea" :rows="2"
                   placeholder="对本节加批注…" />
        <el-button size="small" type="primary" @click="onAdd">加批注</el-button>
      </div>

      <div class="bar">
        <el-tag size="small">未解决 {{ grouped.open.length }}</el-tag>
        <el-tag size="small" type="success">已解决 {{ grouped.resolved.length }}</el-tag>
        <el-tag size="small" type="info">已拒绝 {{ grouped.rejected.length }}</el-tag>
        <el-button size="small" type="warning" :disabled="!openCount"
                   :loading="applying" @click="onApplyAll">
          批量应用 LLM 改 ({{ openCount }})
        </el-button>
      </div>

      <div class="lists">
        <el-collapse>
          <el-collapse-item v-for="(group, k) in grouped" :key="k"
                              :title="`${k} (${group.length})`" :name="k">
            <div v-if="!group.length" class="empty">（无）</div>
            <div v-for="c in group" :key="c.id" class="card">
              <div class="body">{{ c.body }}</div>
              <div class="meta">
                <span class="author">{{ c.author }}</span> ·
                <span class="ts">{{ new Date(c.created_at).toLocaleString('zh-CN') }}</span>
                <span v-if="c.applied_in_draft_version" class="v">
                  · 已落入 v{{ c.applied_in_draft_version }}
                </span>
              </div>
              <div class="ops">
                <el-button text @click="onPatch(c, 'resolved')"
                            :disabled="c.status === 'resolved'">解决</el-button>
                <el-button text @click="onPatch(c, 'rejected')"
                            :disabled="c.status === 'rejected'">拒绝</el-button>
                <el-button text @click="onPatch(c, 'open')"
                            :disabled="c.status === 'open'">重开</el-button>
                <el-button text type="danger" @click="onDelete(c)">删除</el-button>
              </div>
            </div>
          </el-collapse-item>
        </el-collapse>
      </div>
    </template>
  </div>
</template>

<style scoped>
.comments-panel { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.empty { color: #9ca3af; text-align: center; padding: 16px; font-size: 13px; }
.composer { display: flex; gap: 8px; align-items: flex-end; }
.composer .el-input { flex: 1; }
.bar { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.bar .el-button { margin-left: auto; }
.lists :deep(.el-collapse-item__header) { font-size: 13px; }
.card { padding: 8px; background: #fafbfc; border-radius: 6px; border: 1px solid #e5e7eb; margin-bottom: 6px; }
.card .body { font-size: 13px; color: #1f2937; line-height: 1.5; }
.card .meta { color: #6b7280; font-size: 11px; margin-top: 4px; }
.card .ops { margin-top: 4px; display: flex; gap: 4px; }
.card .ops .el-button { padding: 2px 6px; font-size: 11px; }
</style>
