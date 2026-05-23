<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { lookupCoding, type CodingCandidateDTO } from '@/api/rest'

const props = defineProps<{
  open: boolean
  proposal: {
    id: string
    target_columns: string[]
    parameters: Record<string, unknown>
  } | null
}>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'apply', selections: Record<string, string>): void
}>()

interface Mapping {
  original: string
  candidates: CodingCandidateDTO[]
}

const system = ref<string>('MEDDRA')
const mappings = ref<Mapping[]>([])
const selections = ref<Record<string, string>>({})
const refreshing = ref(false)

watch(() => props.proposal, (p) => {
  if (!p) { mappings.value = []; selections.value = {}; return }
  const params = (p.parameters || {}) as Record<string, unknown>
  system.value = String(params.system || 'MEDDRA')
  mappings.value = ((params.mappings as Mapping[]) || []).map((m) => ({
    original: m.original,
    candidates: (m.candidates || []) as CodingCandidateDTO[],
  }))
  selections.value = { ...(params.user_selections as Record<string, string> || {}) }
}, { immediate: true })

const acceptableCount = computed(() => Object.keys(selections.value).length)
const totalCount = computed(() => mappings.value.length)
const highConfidenceCount = computed(() =>
  mappings.value.filter((m) => m.candidates[0] && m.candidates[0].score >= 0.8).length,
)

function choose(orig: string, code: string): void {
  selections.value = { ...selections.value, [orig]: code }
}
function clearChoice(orig: string): void {
  const next = { ...selections.value }
  delete next[orig]
  selections.value = next
}
function acceptHighConfidence(): void {
  const next = { ...selections.value }
  for (const m of mappings.value) {
    const top = m.candidates[0]
    if (top && top.score >= 0.8) next[m.original] = top.code
  }
  selections.value = next
  ElMessage.success(`已为 confidence ≥0.8 的 ${highConfidenceCount.value} 个 term 自动选定`)
}
async function refreshTerm(orig: string): Promise<void> {
  refreshing.value = true
  try {
    const r = await lookupCoding(system.value, orig, 5)
    const idx = mappings.value.findIndex((m) => m.original === orig)
    if (idx >= 0) {
      mappings.value = [
        ...mappings.value.slice(0, idx),
        { original: orig, candidates: r.candidates },
        ...mappings.value.slice(idx + 1),
      ]
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    refreshing.value = false
  }
}
function applyAndClose(): void {
  emit('apply', selections.value)
  emit('update:open', false)
}
function close(): void {
  emit('update:open', false)
}
</script>

<template>
  <el-drawer :model-value="props.open" @update:model-value="(v: boolean) => emit('update:open', v)"
             size="60%" title="查字典 / Map to CDISC">
    <div v-if="!proposal" class="empty">未选择提议</div>
    <div v-else class="drawer">
      <div class="header">
        <div>
          <b>System:</b> {{ system }}
          &nbsp;|&nbsp;
          <b>列:</b> {{ proposal.target_columns.join(', ') }}
        </div>
        <div>
          <el-tag size="small">{{ acceptableCount }} / {{ totalCount }} 已选</el-tag>
          <el-button class="ml" size="small" type="primary"
                     :disabled="!highConfidenceCount" @click="acceptHighConfidence">
            批量接受 confidence ≥0.8 ({{ highConfidenceCount }})
          </el-button>
        </div>
      </div>

      <el-table :data="mappings" stripe size="small" class="terms-table">
        <el-table-column label="原始 term" width="220">
          <template #default="{ row }">
            <div class="term">{{ row.original }}</div>
            <el-button link size="small" :loading="refreshing"
                       @click="refreshTerm(row.original)">重查</el-button>
          </template>
        </el-table-column>
        <el-table-column label="候选 code">
          <template #default="{ row }">
            <div class="cands">
              <div v-for="c in row.candidates" :key="c.code" class="cand">
                <div class="cand-main">
                  <code class="code">{{ c.code }}</code>
                  <span class="pt">{{ c.preferred_term }}</span>
                  <el-tag size="small"
                          :type="c.score >= 0.9 ? 'success' : (c.score >= 0.7 ? 'warning' : 'info')">
                    {{ c.score.toFixed(2) }}
                  </el-tag>
                </div>
                <div class="cand-hier muted" v-if="c.hierarchy?.length">
                  {{ c.hierarchy.join(' › ') }}
                </div>
                <div class="cand-actions">
                  <el-button v-if="selections[row.original] === c.code"
                             size="small" type="success" plain
                             @click="clearChoice(row.original)">已选 ×</el-button>
                  <el-button v-else size="small" @click="choose(row.original, c.code)">
                    接受
                  </el-button>
                </div>
              </div>
              <div v-if="!row.candidates.length" class="muted">无候选</div>
            </div>
          </template>
        </el-table-column>
      </el-table>

      <div class="footer">
        <el-button @click="close">取消</el-button>
        <el-button type="primary" :disabled="!acceptableCount" @click="applyAndClose">
          保存选择并关闭
        </el-button>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer { padding: 8px 12px 80px; }
.empty { padding: 60px 12px; color: #9ca3af; text-align: center; }
.header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 8px 14px; border-bottom: 1px solid #e5e7eb; margin-bottom: 12px;
}
.ml { margin-left: 8px; }
.terms-table .term { font-weight: 600; color: #111827; word-break: break-all; }
.cands { display: flex; flex-direction: column; gap: 6px; }
.cand {
  background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 4px;
  padding: 6px 10px;
}
.cand-main { display: flex; align-items: center; gap: 8px; }
.code { background: #eef2ff; color: #3730a3; padding: 1px 6px; border-radius: 4px;
        font-weight: 600; font-size: 12px; }
.pt { flex: 1; color: #1f2937; }
.cand-hier { font-size: 11px; margin-top: 2px; }
.cand-actions { margin-top: 4px; text-align: right; }
.muted { color: #9ca3af; }
.footer {
  position: absolute; bottom: 0; left: 0; right: 0;
  padding: 12px 24px; background: #fff; border-top: 1px solid #e5e7eb;
  display: flex; justify-content: flex-end; gap: 8px;
}
</style>
