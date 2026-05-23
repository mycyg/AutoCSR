<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createPlan, getPlan, patchPlan, refineFromPlan,
  type SectionPlanDTO, type PlanPointDTO,
} from '@/api/rest'

const props = defineProps<{
  projectId: string
  nodeId: string | null
  outlineTitle?: string | null
}>()

const emit = defineEmits<{
  (e: 'refined'): void
}>()

const plan = ref<SectionPlanDTO | null>(null)
const loading = ref(false)
const refining = ref(false)

async function refresh(): Promise<void> {
  if (!props.nodeId) {
    plan.value = null
    return
  }
  try {
    plan.value = await getPlan(props.projectId, props.nodeId)
  } catch {
    plan.value = null
  }
}

watch(() => props.nodeId, () => { void refresh() }, { immediate: true })

async function onGenerate(): Promise<void> {
  if (!props.nodeId) return
  loading.value = true
  try {
    plan.value = await createPlan(props.projectId, props.nodeId)
    ElMessage.success('计划已生成')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

async function onSave(): Promise<void> {
  if (!props.nodeId || !plan.value) return
  try {
    plan.value = await patchPlan(props.projectId, props.nodeId, {
      points: plan.value.points,
      notes: plan.value.notes,
    })
    ElMessage.success('计划已保存')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

async function onRefine(): Promise<void> {
  if (!props.nodeId || !plan.value) return
  const ok = await ElMessageBox.confirm(
    '将按当前计划生成本节正文，可能覆盖现有 draft。继续？',
    '确认撰写',
    { type: 'warning' },
  ).then(() => true).catch(() => false)
  if (!ok) return
  refining.value = true
  try {
    await refineFromPlan(props.projectId, props.nodeId)
    ElMessage.success('已根据计划生成 draft')
    emit('refined')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    refining.value = false
  }
}

function addPoint(): void {
  if (!plan.value) return
  plan.value.points.push({
    id: 'p_' + Math.random().toString(36).slice(2, 9),
    text: '',
    evidence_hints: [],
    stat_refs_hint: [],
    status: 'edited',
  } as PlanPointDTO)
}

function removePoint(idx: number): void {
  if (!plan.value) return
  plan.value.points.splice(idx, 1)
}

const hasPlan = computed(() => plan.value !== null && plan.value.points.length > 0)
</script>

<template>
  <div class="plan-panel">
    <div v-if="!nodeId" class="empty">请先选择章节</div>
    <template v-else>
      <div class="header">
        <div class="title">
          <span class="node-id">{{ nodeId }}</span>
          <span class="ot">{{ outlineTitle || '' }}</span>
        </div>
        <div class="actions">
          <el-button size="small" :loading="loading" @click="onGenerate">
            {{ hasPlan ? '重新生成' : '生成计划' }}
          </el-button>
          <el-button size="small" type="primary" :disabled="!hasPlan"
                     @click="onSave">保存编辑</el-button>
          <el-button size="small" type="success" :disabled="!hasPlan"
                     :loading="refining" @click="onRefine">撰写</el-button>
        </div>
      </div>

      <div v-if="!hasPlan" class="empty">尚无计划。点「生成计划」让 writer LLM 列出 5-8 个写作点。</div>

      <div v-else class="points">
        <div v-for="(pt, i) in plan!.points" :key="pt.id" class="point">
          <div class="bar">
            <span class="num">{{ i + 1 }}</span>
            <el-tag size="small" :type="pt.status === 'accepted' ? 'success' : pt.status === 'edited' ? 'warning' : 'info'">
              {{ pt.status }}
            </el-tag>
            <el-button text @click="removePoint(i)">删除</el-button>
          </div>
          <el-input v-model="pt.text" type="textarea" :rows="2"
                    placeholder="该段要讲什么 (50-150 字)" />
          <div class="hints">
            <span v-if="pt.stat_refs_hint.length" class="hint stat">
              统计: {{ pt.stat_refs_hint.join(', ') }}
            </span>
            <span v-if="pt.evidence_hints.length" class="hint lit">
              证据: {{ pt.evidence_hints.join(', ') }}
            </span>
          </div>
        </div>
        <el-button size="small" plain @click="addPoint">+ 增加一点</el-button>
      </div>

      <div v-if="plan?.notes" class="notes">
        <div class="label">总体备注</div>
        <el-input v-model="plan.notes" type="textarea" :rows="2" />
      </div>
    </template>
  </div>
</template>

<style scoped>
.plan-panel { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.empty { color: #9ca3af; text-align: center; padding: 24px; font-size: 13px; }
.header { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.title .node-id { font-weight: 600; color: #1d4ed8; margin-right: 6px; font-size: 13px; }
.title .ot { color: #6b7280; font-size: 12px; }
.points { display: flex; flex-direction: column; gap: 10px; }
.point { padding: 8px; background: #fafbfc; border: 1px solid #e5e7eb; border-radius: 6px; }
.point .bar { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
.point .num { display: inline-flex; align-items: center; justify-content: center; width: 22px; height: 22px;
              border-radius: 50%; background: #1d4ed8; color: #fff; font-size: 11px; }
.hints { margin-top: 4px; display: flex; gap: 6px; flex-wrap: wrap; font-size: 11px; color: #6b7280; }
.hint.stat { color: #b45309; }
.hint.lit { color: #16a34a; }
.notes .label { font-size: 12px; color: #6b7280; margin-bottom: 4px; }
</style>
