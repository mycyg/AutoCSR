<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { runAnalysis } from '@/api/rest'

const props = defineProps<{ open: boolean; projectId: string }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void; (e: 'submitted'): void }>()

const visible = computed({
  get: () => props.open,
  set: (v: boolean) => emit('update:open', v),
})

const type = ref<'descriptive' | 'inferential' | 'survival_km' | 'survival_cox' | 'safety'>('descriptive')
const parquetPath = ref('')
const groupCol = ref('TRT01P')
const valueCol = ref('AGE')
const cont = ref('AGE,HEIGHT,WEIGHT,BMI')
const cat = ref('SEX,RACE')
const test = ref<'auto' | 't' | 'wilcoxon' | 'chi2' | 'fisher'>('auto')
const timeCol = ref('AVAL')
const eventCol = ref('CNSR')
const covariates = ref('AGE,SEX')
const subjectCol = ref('USUBJID')
const socCol = ref('AESOC')
const ptCol = ref('AEDECOD')
const sevCol = ref('AESEV')
const relCol = ref('AEREL')
const filterQuery = ref('')
const submitting = ref(false)

watch(() => props.open, (v) => {
  if (!v) submitting.value = false
})

async function submit(): Promise<void> {
  if (!parquetPath.value.trim()) {
    ElMessage.warning('请填写 processed parquet 路径')
    return
  }
  submitting.value = true
  try {
    const params: Record<string, unknown> = { parquet_path: parquetPath.value.trim() }
    if (filterQuery.value.trim()) params.filter_query = filterQuery.value.trim()
    if (type.value === 'descriptive') {
      params.group_col = groupCol.value
      params.cont_cols = cont.value.split(',').map((s) => s.trim()).filter(Boolean)
      params.cat_cols = cat.value.split(',').map((s) => s.trim()).filter(Boolean)
    } else if (type.value === 'inferential') {
      params.group_col = groupCol.value
      params.value_col = valueCol.value
      params.test = test.value
    } else if (type.value === 'survival_km') {
      params.time_col = timeCol.value
      params.event_col = eventCol.value
      params.group_col = groupCol.value || undefined
    } else if (type.value === 'survival_cox') {
      params.time_col = timeCol.value
      params.event_col = eventCol.value
      params.covariates = covariates.value.split(',').map((s) => s.trim()).filter(Boolean)
    } else if (type.value === 'safety') {
      params.soc_col = socCol.value
      params.pt_col = ptCol.value
      params.sev_col = sevCol.value
      params.rel_col = relCol.value
      params.subject_col = subjectCol.value
      params.group_col = groupCol.value || undefined
    }
    await runAnalysis(props.projectId, type.value, params)
    ElMessage.success('分析已完成')
    emit('submitted')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="手动新增分析" width="540px" :destroy-on-close="true">
    <el-form label-width="120px">
      <el-form-item label="分析类型">
        <el-select v-model="type" style="width: 220px">
          <el-option label="描述统计（baseline_table）" value="descriptive" />
          <el-option label="组间检验（compare_groups）" value="inferential" />
          <el-option label="Kaplan-Meier" value="survival_km" />
          <el-option label="Cox 比例风险" value="survival_cox" />
          <el-option label="AE 汇总" value="safety" />
        </el-select>
      </el-form-item>
      <el-form-item label="parquet 路径" required>
        <el-input v-model="parquetPath" placeholder="data/projects/<pid>/processed/<file_id>.parquet" />
      </el-form-item>
      <el-form-item label="过滤表达式" v-if="type !== 'safety'">
        <el-input v-model="filterQuery" placeholder="可选，如 SAFFL == 'Y'" />
      </el-form-item>

      <template v-if="type === 'descriptive'">
        <el-form-item label="分组列"><el-input v-model="groupCol" /></el-form-item>
        <el-form-item label="连续变量">
          <el-input v-model="cont" placeholder="逗号分隔，如 AGE,HEIGHT,WEIGHT,BMI" />
        </el-form-item>
        <el-form-item label="分类变量">
          <el-input v-model="cat" placeholder="逗号分隔，如 SEX,RACE" />
        </el-form-item>
      </template>

      <template v-if="type === 'inferential'">
        <el-form-item label="分组列"><el-input v-model="groupCol" /></el-form-item>
        <el-form-item label="目标列"><el-input v-model="valueCol" /></el-form-item>
        <el-form-item label="检验方法">
          <el-select v-model="test" style="width: 200px">
            <el-option label="自动选择" value="auto" />
            <el-option label="t 检验" value="t" />
            <el-option label="Wilcoxon" value="wilcoxon" />
            <el-option label="卡方" value="chi2" />
            <el-option label="Fisher" value="fisher" />
          </el-select>
        </el-form-item>
      </template>

      <template v-if="type === 'survival_km'">
        <el-form-item label="时间列"><el-input v-model="timeCol" /></el-form-item>
        <el-form-item label="事件列"><el-input v-model="eventCol" /></el-form-item>
        <el-form-item label="分组列"><el-input v-model="groupCol" placeholder="留空 = 不分组" /></el-form-item>
      </template>

      <template v-if="type === 'survival_cox'">
        <el-form-item label="时间列"><el-input v-model="timeCol" /></el-form-item>
        <el-form-item label="事件列"><el-input v-model="eventCol" /></el-form-item>
        <el-form-item label="协变量">
          <el-input v-model="covariates" placeholder="逗号分隔" />
        </el-form-item>
      </template>

      <template v-if="type === 'safety'">
        <el-form-item label="USUBJID 列"><el-input v-model="subjectCol" /></el-form-item>
        <el-form-item label="SOC 列"><el-input v-model="socCol" /></el-form-item>
        <el-form-item label="PT 列"><el-input v-model="ptCol" /></el-form-item>
        <el-form-item label="严重度列"><el-input v-model="sevCol" /></el-form-item>
        <el-form-item label="相关性列"><el-input v-model="relCol" /></el-form-item>
        <el-form-item label="分组列"><el-input v-model="groupCol" placeholder="留空 = 不分组" /></el-form-item>
      </template>
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">运行</el-button>
    </template>
  </el-dialog>
</template>
