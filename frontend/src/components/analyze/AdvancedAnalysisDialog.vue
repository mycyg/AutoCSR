<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  runBaselineBalance, runConsort, runMultitest, runSensitivity, runSubgroup,
} from '@/api/rest'

const props = defineProps<{
  open: boolean
  projectId: string
  kind: 'multitest' | 'subgroup' | 'sensitivity' | 'consort' | 'baseline_balance' | ''
}>()
const emit = defineEmits<{
  (e: 'update:open', v: boolean): void
  (e: 'done'): void
}>()

const submitting = ref(false)

// shared
const fileId = ref<string>('')
const outcomeCol = ref<string>('AVAL')
const groupCol = ref<string>('TRT01P')
const subgroupCols = ref<string>('SEX,AGEGR1')
const sensitivityMethods = ref<string[]>(['itt', 'pp', 'locf', 'mmrm'])
const balanceVars = ref<string>('AGE,HEIGHT,WEIGHT')
const pValuesText = ref<string>('0.01, 0.03, 0.05, 0.08, 0.10')
const labels = ref<string>('')
const method = ref<string>('fdr_bh')

watch(() => props.kind, () => { /* keep defaults */ })

const titleMap: Record<string, string> = {
  multitest: '多重比较校正',
  subgroup: '亚组分析',
  sensitivity: '敏感性分析',
  consort: 'CONSORT 流程',
  baseline_balance: '基线平衡（SMD）',
}

async function submit(): Promise<void> {
  submitting.value = true
  try {
    if (props.kind === 'multitest') {
      const ps = pValuesText.value.split(/[\s,]+/).filter(Boolean).map(Number)
      if (ps.some(isNaN)) throw new Error('p_values 含非数字')
      const lbls = labels.value.split(/[\s,]+/).filter(Boolean)
      await runMultitest(props.projectId, ps, method.value, lbls.length ? lbls : undefined)
    } else if (props.kind === 'subgroup') {
      const sgs = subgroupCols.value.split(/[\s,]+/).filter(Boolean)
      await runSubgroup(props.projectId, outcomeCol.value, groupCol.value, sgs, fileId.value || undefined)
    } else if (props.kind === 'sensitivity') {
      await runSensitivity(props.projectId, outcomeCol.value, groupCol.value,
                             sensitivityMethods.value, fileId.value || undefined)
    } else if (props.kind === 'consort') {
      await runConsort(props.projectId)
    } else if (props.kind === 'baseline_balance') {
      const vs = balanceVars.value.split(/[\s,]+/).filter(Boolean)
      await runBaselineBalance(props.projectId, groupCol.value, vs, fileId.value || undefined)
    }
    ElMessage.success(`${titleMap[props.kind] || ''} 已完成`)
    emit('done')
    emit('update:open', false)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog :model-value="props.open" @update:model-value="(v: boolean) => emit('update:open', v)"
             :title="titleMap[props.kind] || '高级分析'" width="540px">
    <el-form label-width="120" label-position="right" size="small">
      <template v-if="props.kind === 'multitest'">
        <el-form-item label="p-values">
          <el-input v-model="pValuesText" placeholder="0.01, 0.03, 0.05, 0.08, 0.10" />
        </el-form-item>
        <el-form-item label="Method">
          <el-select v-model="method">
            <el-option label="Benjamini-Hochberg (FDR)" value="fdr_bh" />
            <el-option label="Benjamini-Yekutieli (FDR)" value="fdr_by" />
            <el-option label="Bonferroni" value="bonferroni" />
            <el-option label="Holm" value="holm" />
            <el-option label="Hochberg" value="hochberg" />
          </el-select>
        </el-form-item>
        <el-form-item label="Labels (可选)">
          <el-input v-model="labels" placeholder="Test1, Test2 …" />
        </el-form-item>
      </template>

      <template v-else-if="props.kind === 'subgroup'">
        <el-form-item label="file_id (可选)">
          <el-input v-model="fileId" placeholder="留空则用第一个 parquet" />
        </el-form-item>
        <el-form-item label="outcome_col">
          <el-input v-model="outcomeCol" />
        </el-form-item>
        <el-form-item label="group_col">
          <el-input v-model="groupCol" />
        </el-form-item>
        <el-form-item label="subgroup_cols">
          <el-input v-model="subgroupCols" placeholder="SEX, AGEGR1" />
        </el-form-item>
      </template>

      <template v-else-if="props.kind === 'sensitivity'">
        <el-form-item label="file_id (可选)">
          <el-input v-model="fileId" />
        </el-form-item>
        <el-form-item label="outcome_col">
          <el-input v-model="outcomeCol" />
        </el-form-item>
        <el-form-item label="group_col">
          <el-input v-model="groupCol" />
        </el-form-item>
        <el-form-item label="Methods">
          <el-checkbox-group v-model="sensitivityMethods">
            <el-checkbox value="itt">ITT</el-checkbox>
            <el-checkbox value="pp">PP</el-checkbox>
            <el-checkbox value="locf">LOCF</el-checkbox>
            <el-checkbox value="mmrm">MMRM</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </template>

      <template v-else-if="props.kind === 'baseline_balance'">
        <el-form-item label="file_id (可选)">
          <el-input v-model="fileId" />
        </el-form-item>
        <el-form-item label="group_col">
          <el-input v-model="groupCol" />
        </el-form-item>
        <el-form-item label="vars">
          <el-input v-model="balanceVars" placeholder="AGE, HEIGHT, WEIGHT" />
        </el-form-item>
      </template>

      <template v-else-if="props.kind === 'consort'">
        <p>将自动扫描 processed/ 下所有 parquet 并按 ADSL 标志推断 CONSORT 各阶段。</p>
      </template>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:open', false)">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">执行</el-button>
    </template>
  </el-dialog>
</template>
