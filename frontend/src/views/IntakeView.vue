<script setup lang="ts">
import { onMounted, onUnmounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useIngestStore } from '@/stores/ingest'
import { connectProjectWS } from '@/api/ws'

const props = defineProps<{ id: string }>()
const router = useRouter()
const store = useIngestStore()

const pending = ref<File[]>([])
const uploading = ref(false)

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
  // Belt-and-braces poll: 2s tick in case WS doesn't connect (proxy / cors)
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

function onFilesChosen(uploadFile: { raw?: File }, files: { raw?: File }[]): void {
  pending.value = files.map((f) => f.raw).filter((f): f is File => Boolean(f))
}

async function doUpload(): Promise<void> {
  if (!pending.value.length) {
    ElMessage.warning('请先选择文件')
    return
  }
  uploading.value = true
  try {
    await store.upload(props.id, pending.value)
    ElMessage.success(`已上传 ${pending.value.length} 个文件`)
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
    case 'uploaded': return { type: 'info', label: '已上传' }
    case 'routing':  return { type: 'warning', label: '判型中' }
    case 'running':  return { type: 'primary', label: '解析中' }
    case 'done':     return { type: 'success', label: '完成' }
    case 'error':    return { type: 'danger',  label: '错误' }
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
</script>

<template>
  <div class="intake">
    <header class="bar">
      <h2>1. 上传与判型</h2>
      <div class="hint">
        支持 SAS xpt/sas7bdat、CSV/Excel、PDF、Word、纯文本。Router 会自动判型并启动对应 worker。
      </div>
    </header>

    <el-upload
      class="dropzone"
      drag multiple :auto-upload="false"
      :on-change="onFilesChosen"
      :show-file-list="true"
    >
      <el-icon class="upicon"><svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2"/></svg></el-icon>
      <div class="el-upload__text">拖拽文件到此处，或 <em>点击选择</em></div>
      <template #tip>
        <div class="tip">所有文件留在本地，可包含 PII（清洗工作台会强制脱敏）。</div>
      </template>
    </el-upload>

    <div class="actions">
      <el-button type="primary" :loading="uploading"
                 :disabled="!pending.length" @click="doUpload">
        上传并开始判型 ({{ pending.length }})
      </el-button>
      <el-button :disabled="!allDone" type="success" @click="goCleanse">
        下一步：进入清洗 →
      </el-button>
    </div>

    <el-table :data="store.files" class="grid" stripe empty-text="还没有文件">
      <el-table-column prop="filename" label="文件名" min-width="260" />
      <el-table-column label="判型" width="140">
        <template #default="{ row }">
          <el-tag v-if="row.ingest_type" :type="row.needs_user_confirm ? 'warning' : 'primary'">
            {{ TYPE_LABEL[row.ingest_type] || row.ingest_type }}
          </el-tag>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="置信度" width="100">
        <template #default="{ row }">
          <span v-if="row.ingest_confidence !== null">
            {{ (row.ingest_confidence * 100).toFixed(0) }}%
          </span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="大小" width="100">
        <template #default="{ row }">{{ (row.size_bytes / 1024).toFixed(1) }} KB</template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.status).type" size="small">
            {{ statusTag(row.status).label }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="说明" min-width="200">
        <template #default="{ row }">
          <span v-if="row.error" class="err">{{ row.error }}</span>
          <span v-else-if="row.needs_user_confirm" class="warn">请人工确认判型</span>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
    </el-table>
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
.muted { color: #9ca3af; }
.warn { color: #b45309; }
.err { color: #b91c1c; font-size: 12px; }
</style>
