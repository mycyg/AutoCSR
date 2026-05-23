<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useIngestStore } from '@/stores/ingest'
import { connectProjectWS } from '@/api/ws'
import {
  commitCsrImport, importCsrDocx,
  type ImportCsrResultDTO, type ImportCsrSectionDTO,
} from '@/api/rest'

const props = defineProps<{ id: string }>()
const router = useRouter()
const store = useIngestStore()
const { t } = useI18n()

const pending = ref<File[]>([])
const uploading = ref(false)
const tab = ref<'upload' | 'import'>('upload')

let wsClose: (() => void) | null = null
let pollFallback = false

onMounted(async () => {
  await store.refresh(props.id)
  wsClose = connectProjectWS(props.id, (ev) => {
    if (ev.type === 'router.file_classified' || ev.type === 'worker.done'
        || ev.type === 'worker.error' || ev.type === 'router.all_done'
        || ev.type === 'worker.start') {
      void store.refresh(props.id)
    }
  })
  setTimeout(() => {
    if (!pollFallback) {
      pollFallback = true
      store.startPoll(props.id)
    }
  }, 2_500)
})
onUnmounted(() => {
  wsClose?.()
  store.stopPoll()
})

function onFilesChosen(_uploadFile: { raw?: File }, files: { raw?: File }[]): void {
  pending.value = files.map((f) => f.raw).filter((f): f is File => Boolean(f))
}

async function doUpload(): Promise<void> {
  if (!pending.value.length) {
    ElMessage.warning(t('intake.drag_or_click'))
    return
  }
  uploading.value = true
  try {
    await store.upload(props.id, pending.value)
    ElMessage.success(String(pending.value.length))
    pending.value = []
    await store.start(props.id)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    uploading.value = false
  }
}

const allDone = computed(() => store.all_done && store.files.length > 0)

function statusTag(s: string): { type: 'info' | 'warning' | 'success' | 'danger' | 'primary'; label: string } {
  switch (s) {
    case 'uploaded': return { type: 'info', label: '↑' }
    case 'routing':  return { type: 'warning', label: '?' }
    case 'running':  return { type: 'primary', label: '…' }
    case 'done':     return { type: 'success', label: '✓' }
    case 'error':    return { type: 'danger',  label: '!' }
    default: return { type: 'info', label: s }
  }
}

const TYPE_LABEL: Record<string, string> = {
  structured_data: '结构化数据',
  messy_tabular: '杂乱表格',
  pdf_form: 'PDF 表单',
  scan_crf: '扫描件',
  handwriting: '含手写',
  literature_doc: '文献/方案',
}

function goCleanse(): void {
  router.push(`/p/${props.id}/cleanse`)
}

// --- CSR reverse import -------------------------------------------------
const csrFile = ref<File | null>(null)
const csrResult = ref<ImportCsrResultDTO | null>(null)
const csrParsing = ref(false)
const csrCommitting = ref(false)

function onCsrFileChosen(uploadFile: { raw?: File }): void {
  csrFile.value = uploadFile.raw || null
}

async function parseCsr(): Promise<void> {
  if (!csrFile.value) {
    ElMessage.warning(t('intake.csr_upload_hint'))
    return
  }
  csrParsing.value = true
  try {
    csrResult.value = await importCsrDocx(props.id, csrFile.value)
    ElMessage.success(`${csrResult.value.n_headings} headings`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    csrParsing.value = false
  }
}

async function commitCsr(): Promise<void> {
  if (!csrResult.value) return
  try {
    await ElMessageBox.confirm(
      `Import ${csrResult.value.n_headings} sections?`,
      t('intake.csr_commit_button'), { type: 'info' },
    )
  } catch { return }
  csrCommitting.value = true
  try {
    const r = await commitCsrImport(props.id, csrResult.value.import_id)
    ElMessage.success(t('intake.csr_commit_success', { n: r.n_outline_nodes }))
    csrResult.value = null
    csrFile.value = null
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    csrCommitting.value = false
  }
}

interface TreeNode { id: string; label: string; children?: TreeNode[] }

function toTree(sections: ImportCsrSectionDTO[]): TreeNode[] {
  return sections.map((s) => ({
    id: s.node_id,
    label: `${s.title}  (${s.word_count} w)`,
    children: s.children?.length ? toTree(s.children) : undefined,
  }))
}

const csrTree = computed<TreeNode[]>(() =>
  csrResult.value ? toTree(csrResult.value.root_sections) : []
)
</script>

<template>
  <div class="intake">
    <header class="bar">
      <h2>{{ $t('intake.title') }}</h2>
      <div class="hint">{{ $t('intake.hint') }}</div>
    </header>

    <el-tabs v-model="tab">
      <el-tab-pane :label="$t('intake.tab_upload')" name="upload">
        <el-upload
          class="dropzone"
          drag multiple :auto-upload="false"
          :on-change="onFilesChosen"
          :show-file-list="true"
        >
          <el-icon class="upicon">
            <svg width="36" height="36" viewBox="0 0 24 24" fill="none"
                 stroke="currentColor" stroke-width="1.6">
              <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2"/>
            </svg>
          </el-icon>
          <div class="el-upload__text">{{ $t('intake.drag_or_click') }}</div>
          <template #tip>
            <div class="tip">{{ $t('intake.drop_tip') }}</div>
          </template>
        </el-upload>

        <div class="actions">
          <el-button type="primary" :loading="uploading"
                     :disabled="!pending.length" @click="doUpload">
            {{ $t('intake.upload_button') }} ({{ pending.length }})
          </el-button>
          <el-button :disabled="!allDone" type="success" @click="goCleanse">
            {{ $t('intake.go_cleanse') }}
          </el-button>
        </div>

        <el-table :data="store.files" class="grid" stripe :empty-text="$t('common.empty')">
          <el-table-column prop="filename" :label="$t('common.name')" min-width="260" />
          <el-table-column label="ingest" width="140">
            <template #default="{ row }">
              <el-tag v-if="row.ingest_type" :type="row.needs_user_confirm ? 'warning' : 'primary'">
                {{ TYPE_LABEL[row.ingest_type] || row.ingest_type }}
              </el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="conf" width="100">
            <template #default="{ row }">
              <span v-if="row.ingest_confidence !== null">
                {{ (row.ingest_confidence * 100).toFixed(0) }}%
              </span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.size')" width="100">
            <template #default="{ row }">{{ (row.size_bytes / 1024).toFixed(1) }} KB</template>
          </el-table-column>
          <el-table-column :label="$t('common.status')" width="120">
            <template #default="{ row }">
              <el-tag :type="statusTag(row.status).type" size="small">
                {{ statusTag(row.status).label }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane :label="$t('intake.tab_import_csr')" name="import">
        <p class="hint">{{ $t('intake.csr_upload_hint') }}</p>
        <el-upload :auto-upload="false" accept=".docx"
                   :on-change="onCsrFileChosen" :show-file-list="false">
          <el-button type="primary" plain>
            {{ csrFile?.name || $t('intake.drag_or_click') }}
          </el-button>
        </el-upload>
        <div class="actions" style="margin-top: 12px;">
          <el-button :loading="csrParsing" :disabled="!csrFile" @click="parseCsr">
            {{ $t('intake.csr_parse_button') }}
          </el-button>
          <el-button v-if="csrResult" type="success" :loading="csrCommitting" @click="commitCsr">
            {{ $t('intake.csr_commit_button') }}
          </el-button>
        </div>

        <div v-if="csrResult" class="csr-result">
          <h4>{{ $t('intake.csr_tree_title') }}
            <span class="muted">
              · headings={{ csrResult.n_headings }} · paragraphs={{ csrResult.n_paragraphs }}
              · tables={{ csrResult.n_tables }} · confidence={{ csrResult.confidence.toFixed(2) }}
            </span>
          </h4>
          <el-tree :data="csrTree" node-key="id" default-expand-all />
        </div>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.intake {
  padding: 24px 32px;
  max-width: 1400px;
  margin: 0 auto;
}
.bar { margin-bottom: 16px; }
.bar h2 { margin: 0; font-size: 18px; color: #1f2937; }
.bar .hint { color: #6b7280; font-size: 13px; margin-top: 4px; }
.dropzone { margin-bottom: 12px; }
.upicon { color: #3b82f6; display: inline-flex; }
.tip { color: #9ca3af; font-size: 12px; }
.actions { display: flex; gap: 12px; margin-bottom: 14px; }
.grid { background: #fff; border-radius: 6px; }
.muted { color: #9ca3af; font-size: 12px; }
.csr-result { margin-top: 12px; background: #fff; border-radius: 6px; padding: 14px 18px; }
.csr-result h4 { margin: 0 0 10px 0; font-size: 14px; color: #1f2937; }
.hint { color: #6b7280; font-size: 13px; margin-bottom: 12px; }
</style>
