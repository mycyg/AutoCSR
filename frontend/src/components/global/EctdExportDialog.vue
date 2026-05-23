<script setup lang="ts">
/**
 * eCTD M5.3.5 packaging dialog (M17).
 *
 * Three optional file uploads (cover letter, investigator statement, ICF).
 * Posts multipart to /export/ectd, waits for the response, then surfaces
 * the download link. Live progress is surfaced separately by
 * TaskProgressOverlay subscribed to `ectd.*` events.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import {
  ectdDownloadUrl, exportEctd, listEctdExports,
  type EctdExportRecordDTO, type EctdExportResultDTO,
} from '@/api/rest'
import { handleApiError } from '@/utils/errors'

const props = defineProps<{ open: boolean; projectId: string }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()
const { t } = useI18n()

const coverFile = ref<File | null>(null)
const invFile = ref<File | null>(null)
const icfFile = ref<File | null>(null)
const busy = ref(false)
const history = ref<EctdExportRecordDTO[]>([])
const lastResult = ref<EctdExportResultDTO | null>(null)

const dialogVisible = computed({
  get: () => props.open,
  set: (v) => emit('update:open', v),
})

async function refreshHistory(): Promise<void> {
  try { history.value = await listEctdExports(props.projectId) }
  catch { history.value = [] }
}

onMounted(refreshHistory)
watch(() => props.open, (v) => { if (v) void refreshHistory() })

function pick(setter: (f: File | null) => void) {
  return (file: { raw?: File }) => setter(file.raw || null)
}

async function onSubmit(): Promise<void> {
  busy.value = true
  try {
    lastResult.value = await exportEctd(props.projectId, {
      cover_letter: coverFile.value,
      investigator_statement: invFile.value,
      icf: icfFile.value,
    })
    ElMessage.success(`${lastResult.value.filename} (${
      (lastResult.value.size_bytes / 1024).toFixed(1)} KB)`)
    await refreshHistory()
  } catch (e) {
    handleApiError(e, 'errors.export_failed')
  } finally { busy.value = false }
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}
</script>

<template>
  <el-dialog v-model="dialogVisible" :title="t('ectd.title')" width="560"
              :close-on-click-modal="false">
    <p class="hint">{{ t('ectd.hint') }}</p>
    <el-form label-width="160px" size="small">
      <el-form-item :label="t('ectd.cover_letter')">
        <el-upload :auto-upload="false" :show-file-list="false"
                    accept=".pdf,.docx,.txt" :on-change="pick((f) => coverFile = f)">
          <el-button>{{ coverFile?.name || t('ectd.pick_file') }}</el-button>
        </el-upload>
      </el-form-item>
      <el-form-item :label="t('ectd.investigator_statement')">
        <el-upload :auto-upload="false" :show-file-list="false"
                    accept=".pdf,.docx,.txt" :on-change="pick((f) => invFile = f)">
          <el-button>{{ invFile?.name || t('ectd.pick_file') }}</el-button>
        </el-upload>
      </el-form-item>
      <el-form-item :label="t('ectd.icf')">
        <el-upload :auto-upload="false" :show-file-list="false"
                    accept=".pdf,.docx,.txt" :on-change="pick((f) => icfFile = f)">
          <el-button>{{ icfFile?.name || t('ectd.pick_file') }}</el-button>
        </el-upload>
      </el-form-item>
    </el-form>

    <div v-if="lastResult" class="result">
      <el-alert type="success" :closable="false">
        <p>{{ lastResult.filename }} · {{ fmtSize(lastResult.size_bytes) }}</p>
        <el-link :href="ectdDownloadUrl(projectId, lastResult.filename)"
                  target="_blank" type="primary">
          ⬇ {{ t('ectd.download') }}
        </el-link>
      </el-alert>
    </div>

    <div v-if="history.length" class="history">
      <h4>{{ t('ectd.history') }}</h4>
      <ul>
        <li v-for="r in history" :key="r.filename">
          <el-link :href="ectdDownloadUrl(projectId, r.filename)"
                    target="_blank">{{ r.filename }}</el-link>
          <span class="muted">{{ fmtSize(r.size_bytes) }}</span>
        </li>
      </ul>
    </div>

    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.cancel') }}</el-button>
      <el-button type="primary" :loading="busy" @click="onSubmit">
        {{ t('ectd.package') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.hint {
  color: var(--color-text-mute);
  font-size: var(--font-size-sm);
  margin: 0 0 12px;
}
.result {
  margin-top: 12px;
}
.result p { margin: 0 0 6px; }
.history {
  margin-top: 16px;
  border-top: 1px solid var(--color-border);
  padding-top: 10px;
}
.history h4 {
  margin: 0 0 6px 0;
  font-size: var(--font-size-sm);
  color: var(--color-text-mute);
  font-weight: 600;
}
.history ul { margin: 0; padding-left: 18px; }
.history li { display: flex; gap: 8px; align-items: center; font-size: var(--font-size-sm); }
.muted { color: var(--color-text-mute); }
</style>
