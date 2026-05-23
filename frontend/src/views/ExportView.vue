<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useExportStore } from '@/stores/export'
import {
  exportDownloadUrl, getExportTemplateConfig, listExportTemplates,
  patchExportTemplateConfig, uploadExportTemplate,
  listTlfExports, runTlfExport, tlfDownloadUrl,
  type DocxTemplateConfigDTO, type ExportOptions, type TLFExportRecordDTO,
  type UploadedTemplateDTO,
} from '@/api/rest'
import { connectProjectWS } from '@/api/ws'
import EctdExportDialog from '@/components/global/EctdExportDialog.vue'
import { confirmAction } from '@/composables/useConfirm'
import { handleApiError } from '@/utils/errors'

const props = defineProps<{ id: string }>()
const exportStore = useExportStore()
let wsClose: (() => void) | null = null

const opts = ref<ExportOptions>({
  include_compliance_note: true,
  include_toc: true,
  include_appendix_cleansing: true,
  include_appendix_analysis: true,
})
const showHallucinationWarnings = ref(false)
const ectdDialogOpen = ref(false)

const cfg = ref<DocxTemplateConfigDTO | null>(null)
const uploadedTemplates = ref<UploadedTemplateDTO[]>([])
const savingCfg = ref(false)
const tlfHistory = ref<TLFExportRecordDTO[]>([])
const tlfBuilding = ref(false)

async function refreshTlf(): Promise<void> {
  try { tlfHistory.value = await listTlfExports(props.id) } catch { tlfHistory.value = [] }
}

async function onBuildTlf(): Promise<void> {
  tlfBuilding.value = true
  try {
    const r = await runTlfExport(props.id)
    ElMessage.success(`${r.filename} (${(r.size_bytes / 1024).toFixed(1)} KB)`)
    await refreshTlf()
  } catch (e) {
    handleApiError(e)
  } finally {
    tlfBuilding.value = false
  }
}

onMounted(async () => {
  await exportStore.refresh(props.id)
  wsClose = connectProjectWS(props.id, (ev) => exportStore.handleWS(ev))
  try {
    cfg.value = await getExportTemplateConfig(props.id)
    uploadedTemplates.value = await listExportTemplates(props.id)
  } catch { /* harmless */ }
  await refreshTlf()
})

onUnmounted(() => {
  wsClose?.()
  exportStore.reset()
})

const fontOptions = [
  'SimSun', 'SimHei', 'Microsoft YaHei', 'KaiTi',
  'Arial', 'Times New Roman', 'Calibri', 'Cambria',
  'Helvetica', 'Georgia',
]

async function saveCfg(patch: Partial<DocxTemplateConfigDTO> & { preset_apply?: string }): Promise<void> {
  savingCfg.value = true
  try {
    cfg.value = await patchExportTemplateConfig(props.id, patch)
  } catch (e) {
    handleApiError(e)
  } finally {
    savingCfg.value = false
  }
}

async function applyPreset(name: string): Promise<void> {
  await saveCfg({ preset_apply: name })
  ElMessage.success(name)
}

async function onUploadTemplate(uploadFile: { raw?: File }): Promise<void> {
  const f = uploadFile.raw
  if (!f) return
  try {
    const rec = await uploadExportTemplate(props.id, f)
    uploadedTemplates.value = [...uploadedTemplates.value, rec]
    await saveCfg({ custom_template_id: rec.id })
    ElMessage.success(rec.filename)
  } catch (e) {
    handleApiError(e)
  }
}

async function onExport(): Promise<void> {
  try {
    const r = await exportStore.trigger(props.id, opts.value)
    ElMessage.success(`${r.filename} (${(r.size_bytes / 1024).toFixed(1)} KB)`)
  } catch (e) {
    handleApiError(e)
  }
}

async function onDelete(filename: string): Promise<void> {
  if (!await confirmAction('export.delete_confirm',
                            { type: 'warning', danger: true, resource_name: filename })) return
  try { await exportStore.remove(props.id, filename) }
  catch (e) { handleApiError(e) }
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function downloadUrl(filename: string): string {
  return exportDownloadUrl(props.id, filename)
}

function phaseToPercent(phase: string): number {
  const map: Record<string, number> = {
    starting: 5, loading_outline: 10, writing_sections: 40,
    references: 70, appendix_a: 80, appendix_b: 88, saving: 95, done: 100,
  }
  for (const k of Object.keys(map)) {
    if (phase.startsWith(k)) return map[k]
  }
  if (phase.startsWith('section:')) {
    const m = phase.match(/section:(\d+)\/(\d+)/)
    if (m) {
      const i = parseInt(m[1], 10), n = parseInt(m[2], 10)
      return Math.min(40 + Math.round((i / n) * 30), 70)
    }
    return 50
  }
  return 0
}

const previewStyle = computed(() => {
  if (!cfg.value) return {}
  return {
    fontFamily: cfg.value.fonts.body,
    fontSize: `${cfg.value.sizes.body}pt`,
    lineHeight: cfg.value.line_spacing,
    color: cfg.value.colors.body,
  }
})
const previewHeadingStyle = computed(() => {
  if (!cfg.value) return {}
  return {
    fontFamily: cfg.value.fonts.heading,
    fontSize: `${cfg.value.sizes.h2}pt`,
    color: cfg.value.colors.heading,
    fontWeight: 600,
  }
})
</script>

<template>
  <div class="export-view">
    <div class="panel">
      <h2>{{ $t('export.title') }}</h2>
      <p class="hint">{{ $t('export.hint') }}</p>
      <div class="options">
        <el-checkbox v-model="opts.include_compliance_note">
          {{ $t('export.include_compliance') }}
        </el-checkbox>
        <el-checkbox v-model="opts.include_toc">{{ $t('export.include_toc') }}</el-checkbox>
        <el-checkbox v-model="opts.include_appendix_cleansing">{{ $t('export.include_appendix_a') }}</el-checkbox>
        <el-checkbox v-model="opts.include_appendix_analysis">{{ $t('export.include_appendix_b') }}</el-checkbox>
        <el-checkbox v-model="showHallucinationWarnings">
          {{ $t('export.show_hallucination_warnings') }}
        </el-checkbox>
      </div>
      <div class="trigger">
        <el-button type="primary" size="large" :loading="exportStore.exporting" @click="onExport">
          {{ exportStore.exporting ? $t('export.generating') : $t('export.generate') }}
        </el-button>
        <span v-if="exportStore.exporting || exportStore.phase !== 'idle'" class="phase">
          <b>{{ exportStore.phase }}</b>
        </span>
      </div>
      <el-progress v-if="exportStore.exporting" :percentage="phaseToPercent(exportStore.phase)"
                   :indeterminate="exportStore.phase === 'starting'" :duration="2" />
    </div>

    <el-collapse v-if="cfg" class="panel">
      <el-collapse-item :title="$t('export.advanced')">
        <div class="presets">
          <span class="muted">{{ $t('export.presets') }}:</span>
          <el-button :type="cfg.preset === 'standard' ? 'primary' : 'default'"
                     size="small" @click="applyPreset('standard')">{{ $t('export.preset_standard') }}</el-button>
          <el-button :type="cfg.preset === 'pharma' ? 'primary' : 'default'"
                     size="small" @click="applyPreset('pharma')">{{ $t('export.preset_pharma') }}</el-button>
          <el-button :type="cfg.preset === 'academic' ? 'primary' : 'default'"
                     size="small" @click="applyPreset('academic')">{{ $t('export.preset_academic') }}</el-button>
          <el-button :type="cfg.preset === 'regulatory' ? 'primary' : 'default'"
                     size="small" @click="applyPreset('regulatory')">{{ $t('export.preset_regulatory') }}</el-button>
        </div>
        <el-form label-width="120" label-position="right" size="small" class="cfg-form">
          <el-form-item :label="$t('export.heading_font')">
            <el-select v-model="cfg.fonts.heading" filterable allow-create
                       @change="(v: string) => saveCfg({ fonts: { ...cfg!.fonts, heading: v } })">
              <el-option v-for="f in fontOptions" :key="f" :value="f" :label="f" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('export.body_font')">
            <el-select v-model="cfg.fonts.body" filterable allow-create
                       @change="(v: string) => saveCfg({ fonts: { ...cfg!.fonts, body: v } })">
              <el-option v-for="f in fontOptions" :key="f" :value="f" :label="f" />
            </el-select>
          </el-form-item>
          <el-form-item :label="$t('export.body_size')">
            <el-input-number v-model="cfg.sizes.body" :min="8" :max="20"
                              @change="(v: number | undefined) => saveCfg({ sizes: { ...cfg!.sizes, body: v ?? 11 } })" />
          </el-form-item>
          <el-form-item :label="$t('export.line_spacing')">
            <el-slider v-model="cfg.line_spacing" :min="1" :max="3" :step="0.25"
                       @change="(v: number | number[]) => saveCfg({ line_spacing: Array.isArray(v) ? v[0] : v })" />
          </el-form-item>
          <el-form-item :label="$t('export.toc_depth')">
            <el-input-number v-model="cfg.toc_depth" :min="1" :max="6"
                              @change="(v: number | undefined) => saveCfg({ toc_depth: v ?? 3 })" />
          </el-form-item>
          <el-form-item :label="$t('export.header_text')">
            <el-input v-model="cfg.header_text" @change="(v: string) => saveCfg({ header_text: v })" />
          </el-form-item>
          <el-form-item :label="$t('export.footer_text')">
            <el-input v-model="cfg.footer_text" @change="(v: string) => saveCfg({ footer_text: v })" />
          </el-form-item>
          <el-form-item :label="$t('export.watermark')">
            <el-input v-model="cfg.watermark" placeholder="CONFIDENTIAL"
                      @change="(v: string) => saveCfg({ watermark: v })" />
          </el-form-item>
          <el-form-item :label="$t('export.show_ai_provenance')">
            <el-switch v-model="cfg.show_ai_provenance"
                       @change="(v: boolean | string | number) => saveCfg({ show_ai_provenance: !!v })" />
          </el-form-item>
        </el-form>

        <div class="upload-row">
          <el-upload :auto-upload="false" :show-file-list="false" accept=".docx"
                     :on-change="onUploadTemplate">
            <el-button>{{ $t('export.upload_template') }}</el-button>
          </el-upload>
          <span v-if="cfg.custom_template_id" class="muted">
            custom: {{ cfg.custom_template_id }}
            <el-button link size="small" :aria-label="$t('common.delete')" @click="saveCfg({ custom_template_id: null })">×</el-button>
          </span>
        </div>

        <div class="preview">
          <h4>{{ $t('export.preview_title') }}</h4>
          <div class="preview-page" :style="previewStyle">
            <div :style="previewHeadingStyle">11.4.2  Demo Heading</div>
            <p>This is a quick style preview using the configured fonts and sizes.</p>
            <p v-if="cfg.header_text" class="muted">[header] {{ cfg.header_text }}</p>
            <p v-if="cfg.footer_text || cfg.watermark" class="muted">
              [footer] {{ cfg.footer_text }}<span v-if="cfg.watermark"> · [{{ cfg.watermark }}]</span>
            </p>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>

    <div class="panel">
      <h3>{{ $t('ectd.title') }}</h3>
      <p class="hint">{{ $t('ectd.hint') }}</p>
      <el-button type="primary" plain @click="ectdDialogOpen = true">
        📦 {{ $t('export.ectd_open') }}
      </el-button>
    </div>

    <div class="panel">
      <h3>TLF 包（Table-Listing-Figure）</h3>
      <p class="hint">把项目内所有 StatBlock 打成 RTF + CSV + define-XML zip 给监管 QC 复核。</p>
      <div class="trigger">
        <el-button type="primary" :loading="tlfBuilding" @click="onBuildTlf">
          {{ tlfBuilding ? '正在生成…' : '生成 TLF zip' }}
        </el-button>
      </div>
      <el-table v-if="tlfHistory.length" :data="tlfHistory" size="small">
        <el-table-column prop="filename" label="文件" />
        <el-table-column label="大小" width="100">
          <template #default="{ row }">{{ fmtSize(row.size_bytes) }}</template>
        </el-table-column>
        <el-table-column prop="created_at" label="创建时间" width="220" />
        <el-table-column label="—" width="120">
          <template #default="{ row }">
            <el-link :href="tlfDownloadUrl(props.id, row.filename)" type="primary" target="_blank">⬇ 下载</el-link>
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="empty">尚无 TLF 包导出记录</p>
    </div>

    <div class="panel">
      <h3>{{ $t('export.history') }}</h3>
      <el-table v-if="exportStore.history.length" :data="exportStore.history" size="small">
        <el-table-column prop="filename" :label="$t('common.name')" />
        <el-table-column :label="$t('common.size')" width="100">
          <template #default="{ row }">{{ fmtSize(row.size_bytes) }}</template>
        </el-table-column>
        <el-table-column prop="n_sections" label="N" width="60" />
        <el-table-column prop="created_at" :label="$t('common.created_at')" width="200" />
        <el-table-column label="—" width="200">
          <template #default="{ row }">
            <el-link :href="downloadUrl(row.filename)" type="primary" target="_blank">⬇</el-link>
            <el-button type="danger" link size="small" :aria-label="$t('common.delete')" @click="onDelete(row.filename)">×</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p v-else class="empty">{{ $t('export.no_history') }}</p>
    </div>

    <EctdExportDialog v-model:open="ectdDialogOpen" :project-id="props.id" />
  </div>
</template>

<style scoped>
.export-view { padding: 24px; max-width: 1100px; margin: 0 auto; }
.panel { background: var(--color-surface); border-radius: var(--radius-lg); padding: 20px 24px; margin-bottom: 18px; box-shadow: var(--shadow-sm); }
.panel h2 { margin: 0 0 6px 0; color: var(--color-text-strong); }
.panel h3 { margin: 0 0 12px 0; color: var(--color-text-strong); font-size: var(--font-size-xl); }
.hint { color: var(--color-text-mute); font-size: var(--font-size-md); margin-bottom: 14px; }
.options { display: flex; flex-direction: column; gap: 6px; margin-bottom: 18px; }
.trigger { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.phase { color: var(--color-text-mute); font-size: var(--font-size-sm); }
.empty { color: var(--color-text-faint); padding: 12px 0; }
.presets { display: flex; gap: 8px; align-items: center; margin: 8px 0 14px; }
.cfg-form { max-width: 520px; }
.muted { color: var(--color-text-faint); font-size: var(--font-size-sm); }
.upload-row { display: flex; gap: 12px; align-items: center; margin: 8px 0 12px; }
.preview { margin-top: 12px; }
.preview h4 { margin: 0 0 6px; font-size: var(--font-size-md); color: var(--color-text-mute); }
.preview-page {
  background: var(--color-surface-2);
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-md);
  padding: 16px 22px;
  min-height: 100px;
}
</style>
