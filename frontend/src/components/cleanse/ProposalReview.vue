<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { DataProfileDTO, IngestResultDTO, ProposalDTO } from '@/api/rest'
import { getIngestResult } from '@/api/rest'
import CodingMapDrawer from '@/components/cleanse/CodingMapDrawer.vue'

const props = defineProps<{
  projectId: string
  fileId: string
  proposals: ProposalDTO[]
}>()
const emit = defineEmits<{
  (e: 'patch', proposalId: string, patch: Partial<ProposalDTO>): void
  (e: 'refresh'): void
}>()

const profile = ref<DataProfileDTO | null>(null)
const allProfiles = ref<DataProfileDTO[]>([])

watch(() => props.fileId, async (fid) => {
  if (!fid) { profile.value = null; allProfiles.value = []; return }
  try {
    const r: IngestResultDTO = await getIngestResult(props.projectId, fid)
    allProfiles.value = r.profiles
    profile.value = r.profiles[0] || null
  } catch {
    profile.value = null
    allProfiles.value = []
  }
}, { immediate: true })

const TYPE_LABEL: Record<string, string> = {
  rename_column: '重命名列',
  cast_dtype: '类型转换',
  unit_convert: '单位换算',
  normalize_value: '取值标准化',
  impute_missing: '缺失填补',
  outlier_flag: '离群标记',
  hash_pii: 'PII 脱敏',
  split_column: '拆分列',
  merge_columns: '合并列',
  derive_column: '派生列',
  map_to_cdisc: '映射到 CDISC',
}

const STATUS_LABEL: Record<string, string> = {
  pending: '待决', accepted: '已接受', rejected: '已拒绝',
  applied: '已应用', edited: '已编辑',
}

function accept(p: ProposalDTO): void {
  emit('patch', p.id, { status: 'accepted' })
}
function reject(p: ProposalDTO): void {
  if (p.mandatory) {
    ElMessage.warning('PII 脱敏为强制项，无法拒绝（可以编辑参数）')
    return
  }
  emit('patch', p.id, { status: 'rejected' })
}

const editing = ref<string>('')
const editParams = ref<string>('')

function startEdit(p: ProposalDTO): void {
  editing.value = p.id
  editParams.value = JSON.stringify(p.parameters, null, 2)
}
function cancelEdit(): void {
  editing.value = ''
  editParams.value = ''
}
function saveEdit(p: ProposalDTO): void {
  try {
    const params = JSON.parse(editParams.value) as Record<string, unknown>
    emit('patch', p.id, { parameters: params, status: 'edited' })
    cancelEdit()
  } catch (e) {
    ElMessage.error('参数 JSON 解析失败: ' + (e instanceof Error ? e.message : String(e)))
  }
}

const sortedProposals = computed(() => [...props.proposals].sort((a, b) => {
  const order: Record<string, number> = { pending: 0, edited: 1, accepted: 2, rejected: 3, applied: 4 }
  return (order[a.status] ?? 9) - (order[b.status] ?? 9)
}))

// CodingMapDrawer wiring (M14)
const drawerOpen = ref(false)
const drawerProposal = ref<ProposalDTO | null>(null)

function openCodingDrawer(p: ProposalDTO): void {
  drawerProposal.value = p
  drawerOpen.value = true
}

function applyCodingSelections(selections: Record<string, string>): void {
  if (!drawerProposal.value) return
  const params = {
    ...(drawerProposal.value.parameters as Record<string, unknown>),
    user_selections: selections,
  }
  emit('patch', drawerProposal.value.id, {
    parameters: params,
    status: Object.keys(selections).length ? 'accepted' : 'edited',
  })
  ElMessage.success(`已选定 ${Object.keys(selections).length} 个 term`)
}
</script>

<template>
  <div class="review">
    <div v-if="profile" class="profile-top">
      <span class="dim">DataProfile · </span>
      <strong>{{ profile.n_rows }}</strong> 行 ×
      <strong>{{ profile.n_cols }}</strong> 列
      <span v-if="profile.encoding_issues.length" class="enc-warn">
        编码异常 × {{ profile.encoding_issues.length }}
      </span>
    </div>

    <el-empty v-if="!proposals.length" description="该文件没有清洗建议" />

    <div v-for="p in sortedProposals" :key="p.id" class="card" :class="`s-${p.status}`">
      <div class="head">
        <el-tag :type="p.mandatory ? 'danger' : 'primary'" size="small">
          {{ TYPE_LABEL[p.type] || p.type }}
        </el-tag>
        <span class="cols">→ {{ p.target_columns.join(', ') }}</span>
        <el-tag size="small" type="info">{{ STATUS_LABEL[p.status] || p.status }}</el-tag>
        <span class="conf">conf {{ (p.confidence * 100).toFixed(0) }}%</span>
        <span class="impact">影响 ≈ {{ p.impact_rows }} 行</span>
      </div>
      <div class="rationale">{{ p.rationale }}</div>
      <div class="params" v-if="editing !== p.id">
        <span class="dim">参数：</span>
        <code>{{ JSON.stringify(p.parameters) }}</code>
      </div>
      <div v-else class="param-edit">
        <el-input v-model="editParams" type="textarea" :rows="4" placeholder="JSON 对象" />
        <div class="param-actions">
          <el-button size="small" @click="cancelEdit">取消</el-button>
          <el-button size="small" type="primary" @click="saveEdit(p)">保存</el-button>
        </div>
      </div>
      <div class="actions" v-if="editing !== p.id">
        <el-button size="small" type="success"
                   :disabled="p.status === 'applied'"
                   @click="accept(p)">接受</el-button>
        <el-button size="small" @click="startEdit(p)" :disabled="p.status === 'applied'">编辑参数</el-button>
        <el-button v-if="p.type === 'map_to_cdisc'" size="small" type="primary" plain
                   :disabled="p.status === 'applied'"
                   @click="openCodingDrawer(p)">查字典</el-button>
        <el-button size="small" type="danger" :disabled="p.mandatory || p.status === 'applied'"
                   @click="reject(p)">
          {{ p.mandatory ? '强制保留' : '拒绝' }}
        </el-button>
      </div>
    </div>
    <CodingMapDrawer v-model:open="drawerOpen" :proposal="drawerProposal" @apply="applyCodingSelections" />
  </div>
</template>

<style scoped>
.review { padding: 12px 14px; overflow: auto; height: 100%; box-sizing: border-box; }
.profile-top { font-size: 12px; color: #4b5563; margin-bottom: 12px; }
.profile-top .dim { color: #9ca3af; }
.profile-top .enc-warn { color: #b45309; margin-left: 12px; }
.card {
  border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px 14px;
  margin-bottom: 10px; background: #fff;
}
.card.s-applied { background: #f8fafc; opacity: 0.85; }
.card.s-rejected { opacity: 0.55; }
.head {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  font-size: 13px; margin-bottom: 6px;
}
.cols { color: #1f2937; font-weight: 500; }
.conf, .impact { color: #6b7280; font-size: 12px; margin-left: auto; }
.impact { margin-left: 8px; }
.rationale { color: #374151; font-size: 13px; margin-bottom: 6px; line-height: 1.5; }
.params { font-size: 12px; color: #4b5563; margin-bottom: 8px; word-break: break-all; }
.params code { background: #f3f4f6; padding: 1px 6px; border-radius: 4px; }
.dim { color: #9ca3af; }
.param-edit { margin-bottom: 8px; }
.param-actions { display: flex; gap: 6px; margin-top: 6px; }
.actions { display: flex; gap: 6px; }
</style>
