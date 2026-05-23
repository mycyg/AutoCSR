<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MdEditor, MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import 'md-editor-v3/lib/style.css'
import { createSnapshot, listSectionVersions, rollbackSection, updateDraftMarkdown,
         type SectionDraftDTO } from '@/api/rest'
import { useShortcuts } from '@/composables/useShortcuts'
import { useI18n } from 'vue-i18n'
import { useRecentlyViewed } from '@/composables/useRecentlyViewed'
import { useResponsive } from '@/composables/useResponsive'
import { useLongPress } from '@/composables/useTouchGestures'
import { handleApiError } from '@/utils/errors'
import { sanitizeMarkdownHtml } from '@/utils/sanitize'
import { Pencil, Save, Copy, MoreHorizontal, Link2 } from 'lucide-vue-next'
const { t } = useI18n()
const { isMobile } = useResponsive()

const props = defineProps<{
  projectId: string
  nodeId: string | null
  draft: SectionDraftDTO | null
  outlineTitle?: string
  compact?: boolean
  highlight?: string
}>()

const emit = defineEmits<{
  (e: 'regenerate', extra?: string): Promise<void> | void
  (e: 'changed'): void
}>()

const showExtra = ref(false)
const extraInstruction = ref('')
const locked = ref(true)
const localMd = ref('')
const versions = ref<number[]>([])
const pickedVersion = ref<number | null>(null)
const saving = ref(false)

const empty = computed(() => !props.draft)

watch(() => props.draft?.markdown, (v) => {
  localMd.value = v || ''
})

watch(() => props.nodeId, async (id) => {
  if (id) {
    await refreshVersions()
    const title = props.draft?.title || props.outlineTitle || id
    try { useRecentlyViewed(props.projectId).track(id, title) } catch { /* sessionStorage may be blocked */ }
  }
  locked.value = true
})

async function refreshVersions(): Promise<void> {
  if (!props.nodeId) return
  try {
    versions.value = await listSectionVersions(props.projectId, props.nodeId)
  } catch {
    versions.value = []
  }
}

let saveTimer: number | null = null
function clearSaveTimer(): void {
  if (saveTimer !== null) {
    window.clearTimeout(saveTimer)
    saveTimer = null
  }
}

function scheduleSave(): void {
  clearSaveTimer()
  saveTimer = window.setTimeout(() => {
    saveTimer = null
    void doSave()
  }, 500)
}

async function doSave(): Promise<void> {
  if (!props.nodeId || locked.value) return
  if (!props.draft || localMd.value === props.draft.markdown) return
  saving.value = true
  try {
    await updateDraftMarkdown(props.projectId, props.nodeId, localMd.value)
    await refreshVersions()
    emit('changed')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    saving.value = false
  }
}

function onEdit(v: string): void {
  localMd.value = v
  scheduleSave()
}

async function toggleLock(): Promise<void> {
  if (!locked.value) {
    // Lock — flush save first
    if (saveTimer !== null) {
      clearSaveTimer()
      await doSave()
    }
  }
  locked.value = !locked.value
}

async function onRollback(): Promise<void> {
  if (!props.nodeId || pickedVersion.value === null) return
  const v = pickedVersion.value
  try {
    await ElMessageBox.confirm(
      `将回滚本节到版本 v${v}，当前内容将被覆盖（不影响已存在的版本快照）。`,
      '版本回滚',
      { type: 'warning' },
    )
  } catch { return }
  try {
    await rollbackSection(props.projectId, props.nodeId, v)
    ElMessage.success(`已回滚到 v${v}`)
    emit('changed')
    await refreshVersions()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onRegenerate(): Promise<void> {
  if (!props.nodeId) return
  try {
    await ElMessageBox.confirm(
      '会调用 writer agent 重新生成本节，旧版本会保留在历史中。',
      '重写本节',
      { type: 'warning' },
    )
  } catch {
    return
  }
  await emit('regenerate', extraInstruction.value || undefined)
  extraInstruction.value = ''
  showExtra.value = false
  await refreshVersions()
}

async function onCopy(): Promise<void> {
  if (!props.draft) return
  try {
    await navigator.clipboard.writeText(localMd.value || props.draft.markdown)
    ElMessage.success(t('report.copied'))
  } catch {
    handleApiError(new Error('copy failed'))
  }
}

async function onShareSnapshot(): Promise<void> {
  if (!props.nodeId) return
  try {
    const snap = await createSnapshot(props.projectId, props.nodeId)
    try { await navigator.clipboard.writeText(snap.url) } catch { /* no clipboard */ }
    ElMessage.success(`${t('report.snapshot_created')}: ${snap.url}`)
  } catch (e) {
    handleApiError(e)
  }
}

// Cmd/Ctrl+S → save current section (only when unlocked)
useShortcuts({
  save: () => {
    if (!locked.value) {
      if (saveTimer !== null) {
        window.clearTimeout(saveTimer)
        saveTimer = null
      }
      void doSave()
    }
  },
})

// M22 — long-press touch -> pop the section context menu (Copy / History / Regenerate).
const readerRoot = ref<HTMLElement | null>(null)
const ctxMenuOpen = ref(false)
const ctxMenuX = ref(0)
const ctxMenuY = ref(0)

function openCtxMenu(pos: { x: number; y: number }): void {
  if (!props.draft) return
  ctxMenuX.value = pos.x
  ctxMenuY.value = pos.y
  ctxMenuOpen.value = true
}
function closeCtxMenu(): void { ctxMenuOpen.value = false }

useLongPress(readerRoot, openCtxMenu, { delay: 500, tolerance: 12 })

const compact = computed(() => !!(props.compact || isMobile.value))

onBeforeUnmount(clearSaveTimer)
</script>

<template>
  <div class="chapter-reader" ref="readerRoot" :class="{ 'is-compact': compact }" :data-highlight="props.highlight || ''">
    <div v-if="empty" class="empty">
      <p v-if="nodeId">本节尚无草稿。</p>
      <p v-else>← 在左侧选择章节</p>
      <el-button v-if="nodeId" type="primary" plain size="small" @click="onRegenerate">
        生成本节
      </el-button>
    </div>
    <template v-else-if="draft">
      <!-- Compact (mobile) toolbar: save/copy/history only; rest in overflow. -->
      <div v-if="compact" class="toolbar toolbar-compact" role="toolbar"
            :aria-label="t('report.toolbar_aria')">
        <span class="title" :title="draft.title || outlineTitle || draft.node_id">
          {{ draft.title || outlineTitle || draft.node_id }}
        </span>
        <span class="spacer" />
        <el-button size="small" :type="locked ? 'default' : 'success'" plain
                   @click="toggleLock" :aria-label="locked ? t('report.edit') : t('common.save')">
          <Pencil v-if="locked" class="lc-icon" />
          <Save v-else class="lc-icon" />
        </el-button>
        <el-button size="small" @click="onCopy" :aria-label="t('report.copy_md')">
          <Copy class="lc-icon" />
        </el-button>
        <el-dropdown trigger="click" @command="(c: string) => {
          if (c === 'history') showExtra = false;
          if (c === 'regen') onRegenerate();
          if (c === 'share') onShareSnapshot();
          if (c === 'extra') showExtra = !showExtra;
        }">
          <el-button size="small" :aria-label="t('common.more')">
            <MoreHorizontal class="lc-icon" />
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="extra">{{ showExtra ? '收起指令' : '+ 指令' }}</el-dropdown-item>
              <el-dropdown-item command="regen">{{ $t('report.regenerate') }}</el-dropdown-item>
              <el-dropdown-item command="share">{{ $t('common.share') }}</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-select v-if="versions.length" v-model="pickedVersion" placeholder="v…" size="small"
                   class="ver-select" clearable :aria-label="$t('report.history')">
          <el-option v-for="v in versions" :key="v" :label="`v${v}`" :value="v" />
        </el-select>
        <el-button v-if="pickedVersion !== null" size="small" @click="onRollback">{{ t('common.rollback') }}</el-button>
      </div>
      <div v-else class="toolbar" role="toolbar"
            :aria-label="t('report.toolbar_aria')">
        <span class="title">{{ draft.title || outlineTitle || draft.node_id }}</span>
        <span class="meta">
          <el-tag size="small" :type="draft.status === 'error' ? 'danger'
                                       : draft.status === 'harmonized' ? 'success' : 'info'">
            {{ draft.status }}
          </el-tag>
          <span class="words">{{ draft.word_count }} 字</span>
          <span class="tokens">tok in {{ draft.llm_meta.tokens_in }} / out {{ draft.llm_meta.tokens_out }}</span>
          <span v-if="saving" class="saving">保存中…</span>
        </span>
        <span class="spacer" />
        <el-select v-model="pickedVersion" placeholder="历史版本" size="small"
                   class="ver-select" clearable :disabled="!versions.length">
          <el-option v-for="v in versions" :key="v" :label="`v${v}`" :value="v" />
        </el-select>
        <el-button size="small" :disabled="pickedVersion === null" @click="onRollback">回滚</el-button>
        <el-button size="small" :type="locked ? 'default' : 'success'" plain
                   @click="toggleLock">
          {{ locked ? '手工微调' : '锁定 (保存)' }}
        </el-button>
        <el-button size="small" plain @click="showExtra = !showExtra">
          {{ showExtra ? '收起' : '+ 指令' }}
        </el-button>
        <el-button size="small" type="primary" plain @click="onRegenerate">重写本节</el-button>
        <el-button size="small" @click="onCopy" :aria-label="t('report.copy_md')">
          <Copy class="lc-icon" /> <span>{{ t('report.copy_md') }}</span>
        </el-button>
        <el-button size="small" @click="onShareSnapshot" :aria-label="t('report.share_snapshot')">
          <Link2 class="lc-icon" /> <span>{{ t('common.share') }}</span>
        </el-button>
      </div>
      <div v-if="showExtra" class="extra">
        <el-input v-model="extraInstruction" type="textarea" :rows="2"
                  placeholder="给 writer 一些额外说明（例：聚焦在安全性叙事；引用 ADAE 表）" />
      </div>
      <div v-if="draft.warnings?.length" class="warnings">
        <el-alert type="warning" :closable="false">
          <ul class="warn-list">
            <li v-for="w in draft.warnings" :key="w">{{ w }}</li>
          </ul>
        </el-alert>
      </div>
      <Transition name="fade" mode="out-in">
        <MdPreview v-if="locked" :key="nodeId + '-r'" class="md"
                   :model-value="localMd" :preview-theme="'github'"
                   :sanitize="sanitizeMarkdownHtml" />
        <MdEditor v-else :key="nodeId + '-e'" class="md editor"
                  :model-value="localMd" :preview-theme="'github'"
                  :sanitize="sanitizeMarkdownHtml" @on-change="onEdit" />
      </Transition>
      <!-- M22 — long-press context menu (mobile). -->
      <Teleport to="body">
        <div v-if="ctxMenuOpen" class="ctx-mask" @click="closeCtxMenu" />
        <ul v-if="ctxMenuOpen" class="ctx-menu" role="menu"
             :style="{ top: ctxMenuY + 'px', left: ctxMenuX + 'px' }">
          <li role="menuitem" @click="() => { onCopy(); closeCtxMenu() }">{{ t('report.copy_md') }}</li>
          <li role="menuitem" @click="() => { onShareSnapshot(); closeCtxMenu() }">{{ t('common.share') }}</li>
          <li role="menuitem" @click="() => { onRegenerate(); closeCtxMenu() }">{{ t('report.regenerate') }}</li>
          <li v-if="!locked" role="menuitem" @click="() => { toggleLock(); closeCtxMenu() }">{{ t('common.save') }}</li>
        </ul>
      </Teleport>
      <div v-if="draft.citations?.length" class="cites">
        <h4>引用</h4>
        <ul>
          <li v-for="c in draft.citations" :key="c.ref_code">
            <code>{{ c.ref_code }}</code>
            <span class="cite-type">[{{ c.type }}]</span>
            <span class="cite-snippet">{{ c.snippet }}</span>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>

<style scoped>
.lc-icon { width: 14px; height: 14px; stroke-width: 1.5; display: inline-block; vertical-align: middle; }
.chapter-reader { height: 100%; display: flex; flex-direction: column; }
.empty { padding: 80px 0; text-align: center; color: var(--color-text-mute); }
.toolbar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px 12px; border-bottom: 1px solid #e5e7eb; background: #fff;
}
.toolbar .title { font-weight: 600; color: #111827; }
.toolbar .meta { display: inline-flex; align-items: center; gap: 8px; font-size: 12px; color: #6b7280; }
.toolbar .words { font-family: ui-monospace, monospace; }
.toolbar .tokens { font-family: ui-monospace, monospace; }
.toolbar .saving { color: #2563eb; font-size: 11px; }
.toolbar .spacer { flex: 1; }
.toolbar .ver-select { width: 100px; }
.extra { padding: 8px 12px; background: #fafbfc; border-bottom: 1px solid #f3f4f6; }
.warnings { padding: 0 12px; margin-top: 8px; }
.warn-list { margin: 0; padding-left: 18px; font-size: 12px; }
.md { flex: 1; overflow: auto; padding: 0 12px; }
.md.editor { padding: 0; }
.cites {
  padding: 8px 12px; background: #fafbfc; border-top: 1px solid #f3f4f6;
  font-size: 12px;
}
.cites h4 { margin: 0 0 6px 0; color: #374151; font-size: 12px; }
.cites ul { margin: 0; padding-left: 18px; }
.cites code { background: #eef2ff; color: #1e3a8a; padding: 0 4px; border-radius: 3px; font-family: ui-monospace, monospace; }
.cites .cite-type { color: #6b7280; margin: 0 6px; }
.cites .cite-snippet { color: #4b5563; }
.fade-enter-active, .fade-leave-active {
  transition: opacity 200ms ease;
}
.fade-enter-from, .fade-leave-to { opacity: 0; }
.chapter-reader.is-compact .toolbar { padding: 6px 8px; }
.chapter-reader.is-compact .toolbar .title {
  font-size: var(--font-size-md);
  max-width: 40%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.chapter-reader.is-compact .ver-select { width: 72px; }
.chapter-reader.is-compact .md { padding: 0 8px; font-size: 14px; }
</style>
<style>
/* Unscoped: the context menu lives under document.body via <Teleport>. */
.ctx-mask {
  position: fixed; inset: 0;
  z-index: 1000;
  background: transparent;
}
.ctx-menu {
  position: fixed;
  z-index: 1001;
  margin: 0;
  padding: 4px 0;
  background: var(--color-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-lg);
  list-style: none;
  min-width: 180px;
  font-size: var(--font-size-md);
}
.ctx-menu li {
  padding: 10px 14px;
  cursor: pointer;
  color: var(--color-text);
}
.ctx-menu li:hover, .ctx-menu li:focus-visible { background: var(--color-surface-3); }
</style>
