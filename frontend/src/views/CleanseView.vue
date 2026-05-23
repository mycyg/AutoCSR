<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useIngestStore } from '@/stores/ingest'
import { useCleansingStore } from '@/stores/cleansing'
import { connectProjectWS } from '@/api/ws'
import FileListPanel from '@/components/cleanse/FileListPanel.vue'
import ProposalReview from '@/components/cleanse/ProposalReview.vue'
import PreviewAndAudit from '@/components/cleanse/PreviewAndAudit.vue'
import BatchActions from '@/components/cleanse/BatchActions.vue'
import EmptyState from '@/components/global/EmptyState.vue'
import { handleApiError } from '@/utils/errors'
import { useRouter } from 'vue-router'
import { useResponsive } from '@/composables/useResponsive'
import { ref as _ref } from 'vue'
const router = useRouter()
const { isMobile } = useResponsive()
const mobileTab = _ref<'files' | 'review' | 'preview'>('review')

const props = defineProps<{ id: string }>()
const ingest = useIngestStore()
const cleansing = useCleansingStore()

let wsClose: (() => void) | null = null

onMounted(async () => {
  await ingest.refresh(props.id)
  await cleansing.loadAudit(props.id)
  await cleansing.loadSnapshots(props.id)
  await cleansing.loadPipelineYaml(props.id)
  // Auto-select first done file
  const firstDone = ingest.files.find((f) => f.status === 'done')
  if (firstDone && !cleansing.selectedFileId) {
    cleansing.selectedFileId = firstDone.file_id
    await cleansing.loadProposals(props.id, firstDone.file_id)
  }
  wsClose = connectProjectWS(props.id, (ev) => {
    if (ev.type === 'cleansing.apply_done' || ev.type === 'cleansing.rollback') {
      void cleansing.loadAudit(props.id)
      void cleansing.loadSnapshots(props.id)
      if (cleansing.selectedFileId) {
        void cleansing.loadPreview(props.id, cleansing.selectedFileId)
        void cleansing.loadProposals(props.id, cleansing.selectedFileId)
      }
    }
  })
})

onUnmounted(() => { wsClose?.() })

watch(() => cleansing.selectedFileId, async (fid) => {
  if (!fid) return
  await cleansing.loadProposals(props.id, fid)
  await cleansing.loadPreview(props.id, fid)
})

async function onSelect(fid: string): Promise<void> {
  cleansing.selectedFileId = fid
}
async function onPatch(proposalId: string, patch: Record<string, unknown>): Promise<void> {
  try {
    await cleansing.patchProposal(props.id, cleansing.selectedFileId, proposalId, patch)
  } catch (e) {
    handleApiError(e)
  }
}
async function onApply(): Promise<void> {
  try {
    const out = await cleansing.apply(props.id, cleansing.selectedFileId)
    ElMessage.success(`已生成清洗结果，快照 ${out.snapshot_id.slice(0, 8)}`)
    await cleansing.loadPipelineYaml(props.id)
  } catch (e) {
    handleApiError(e)
  }
}
async function onAcceptAll(): Promise<void> {
  try {
    await cleansing.acceptAll(props.id, cleansing.selectedFileId)
    ElMessage.success('已全部接受')
  } catch (e) {
    handleApiError(e)
  }
}
async function onRollbackLatest(): Promise<void> {
  const list = cleansing.snapshots.filter((s) => s.file_id === cleansing.selectedFileId)
  if (!list.length) {
    ElMessage.warning('该文件尚无快照')
    return
  }
  const latest = list[list.length - 1]
  await cleansing.rollback(props.id, latest.id, cleansing.selectedFileId)
  ElMessage.success(`已回滚到 ${latest.id.slice(0, 8)}`)
}
async function onRollback(sid: string): Promise<void> {
  await cleansing.rollback(props.id, sid, cleansing.selectedFileId)
  ElMessage.success(`已回滚到 ${sid.slice(0, 8)}`)
}

const proposals = computed(() => cleansing.proposalsForSelected)
const hasAccepted = computed(() => proposals.value.some(
  (p) => p.status === 'accepted' || p.status === 'edited' || p.mandatory,
))
const hasPending = computed(() => proposals.value.some((p) => p.status === 'pending'))
</script>

<template>
  <div class="cleanse">
    <EmptyState v-if="!ingest.files.length"
                 icon="🗂"
                 :title="$t('cleanse.empty_title')"
                 :description="$t('cleanse.empty_desc')"
                 :cta-text="$t('cleanse.go_upload')"
                 @cta="router.push(`/p/${props.id}/intake`)" />
    <template v-else>
      <!-- Mobile: tabbed single-pane. -->
      <template v-if="isMobile">
        <el-tabs v-model="mobileTab" class="m-tabs">
          <el-tab-pane :label="$t('cleanse.tab_files')" name="files" />
          <el-tab-pane :label="$t('cleanse.tab_review')" name="review" />
          <el-tab-pane :label="$t('cleanse.tab_preview')" name="preview" />
        </el-tabs>
        <div class="m-pane">
          <FileListPanel v-if="mobileTab === 'files'"
            :files="ingest.files"
            :proposals-by-file="cleansing.proposalsByFile"
            :selected-file-id="cleansing.selectedFileId"
            @select="onSelect" />
          <template v-else-if="mobileTab === 'review'">
            <div v-if="!cleansing.selectedFileId" class="empty-hint">
              ← {{ $t('cleanse.pick_file_first') }}
            </div>
            <ProposalReview v-else
              :project-id="props.id"
              :file-id="cleansing.selectedFileId"
              :proposals="proposals"
              @patch="onPatch" />
          </template>
          <PreviewAndAudit v-else
            :project-id="props.id"
            :file-id="cleansing.selectedFileId"
            :preview-columns="cleansing.previewCols"
            :preview-rows="cleansing.previewRows"
            :audit="cleansing.audit"
            :snapshots="cleansing.snapshots.filter((s) => s.file_id === cleansing.selectedFileId)"
            :pipeline-yaml="cleansing.pipelineYaml"
            @refreshPreview="cleansing.loadPreview(props.id, cleansing.selectedFileId)"
            @refreshYaml="cleansing.loadPipelineYaml(props.id)"
            @rollback="onRollback" />
        </div>
      </template>
      <el-container v-else class="three-pane">
        <el-aside class="left" width="260px">
          <FileListPanel
            :files="ingest.files"
            :proposals-by-file="cleansing.proposalsByFile"
            :selected-file-id="cleansing.selectedFileId"
            @select="onSelect"
          />
        </el-aside>
        <el-main class="center">
          <div v-if="!cleansing.selectedFileId" class="empty-hint">
            ← 在左侧选择一个文件，开始审阅清洗建议
          </div>
          <ProposalReview
            v-else
            :project-id="props.id"
            :file-id="cleansing.selectedFileId"
            :proposals="proposals"
            @patch="onPatch"
          />
        </el-main>
        <el-aside class="right" width="460px">
          <PreviewAndAudit
            :project-id="props.id"
            :file-id="cleansing.selectedFileId"
            :preview-columns="cleansing.previewCols"
            :preview-rows="cleansing.previewRows"
            :audit="cleansing.audit"
            :snapshots="cleansing.snapshots.filter((s) => s.file_id === cleansing.selectedFileId)"
            :pipeline-yaml="cleansing.pipelineYaml"
            @refreshPreview="cleansing.loadPreview(props.id, cleansing.selectedFileId)"
            @refreshYaml="cleansing.loadPipelineYaml(props.id)"
            @rollback="onRollback"
          />
        </el-aside>
      </el-container>
    </template>
    <BatchActions v-if="ingest.files.length"
      :file-id="cleansing.selectedFileId"
      :has-accepted="hasAccepted"
      :has-pending="hasPending"
      @apply="onApply"
      @accept-all="onAcceptAll"
      @rollback-latest="onRollbackLatest"
    />
  </div>
</template>

<style scoped>
.cleanse {
  display: flex; flex-direction: column;
  height: calc(100vh - 56px);
}
.three-pane { flex: 1; overflow: hidden; }
.left { background: var(--color-surface); border-right: 1px solid var(--color-border); overflow: auto; }
.center { background: var(--color-surface-2); padding: 0; overflow: auto; }
.right { background: var(--color-surface); border-left: 1px solid var(--color-border); overflow: auto; }
.empty-hint {
  color: var(--color-text-mute); padding: 60px 24px; text-align: center;
}
@media (max-width: 1279px) {
  .left { width: 220px !important; }
  .right { width: 320px !important; }
}
@media (max-width: 1023px) {
  .three-pane { flex-direction: column; }
  .left, .right { width: auto !important; max-height: 220px; border: none; border-bottom: 1px solid var(--color-border); }
}
@media (max-width: 767px) {
  .cleanse { height: calc(100dvh - 48px); font-size: 14px; }
}
.m-tabs { background: var(--color-surface); border-bottom: 1px solid var(--color-border); }
.m-tabs :deep(.el-tabs__header) { margin: 0; }
.m-pane { flex: 1; overflow: auto; padding: 8px; }
</style>
