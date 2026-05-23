<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAnalysisStore } from '@/stores/analysis'
import { connectProjectWS } from '@/api/ws'
import StatBlockDrawer from '@/components/analyze/StatBlockDrawer.vue'
import ManualAnalysisDialog from '@/components/analyze/ManualAnalysisDialog.vue'
import DataAskPanel from '@/components/analyze/DataAskPanel.vue'
import AdvancedAnalysisDialog from '@/components/analyze/AdvancedAnalysisDialog.vue'
import EmptyState from '@/components/global/EmptyState.vue'
import { confirmAction } from '@/composables/useConfirm'
import { handleApiError } from '@/utils/errors'
import { useI18n } from 'vue-i18n'
import { useResponsive } from '@/composables/useResponsive'
const { t } = useI18n()
const { isMobile } = useResponsive()
void isMobile  // referenced via CSS media query; keep composable mounted

const props = defineProps<{ id: string }>()
const analysis = useAnalysisStore()

const drawerOpen = ref(false)
const manualOpen = ref(false)
const advancedOpen = ref(false)
const advancedKind = ref<'' | 'multitest' | 'subgroup' | 'sensitivity' | 'consort' | 'baseline_balance'>('')
let wsClose: (() => void) | null = null

function openAdvanced(kind: 'multitest' | 'subgroup' | 'sensitivity' | 'consort' | 'baseline_balance'): void {
  advancedKind.value = kind
  advancedOpen.value = true
}

const typeColor: Record<string, string> = {
  descriptive: '',
  inferential: 'success',
  survival: 'warning',
  safety: 'danger',
  custom: 'info',
  multitest: 'info',
  subgroup: 'success',
  sensitivity: 'warning',
  consort: '',
  baseline_balance: 'info',
}

const typeLabel: Record<string, string> = {
  descriptive: '描述统计',
  inferential: '组间检验',
  survival: '生存分析',
  safety: '安全性',
  custom: '自定义',
  multitest: '多重比较',
  subgroup: '亚组分析',
  sensitivity: '敏感性',
  consort: 'CONSORT',
  baseline_balance: '基线平衡',
}

const sortedBlocks = computed(() => [...analysis.blocks])

onMounted(async () => {
  await analysis.refresh(props.id)
  wsClose = connectProjectWS(props.id, (ev) => {
    if (ev.type === 'analysis.done' || ev.type === 'analysis.error') {
      void analysis.refresh(props.id)
    }
  })
})

onUnmounted(() => { wsClose?.(); analysis.reset() })

async function onAuto(): Promise<void> {
  try {
    await analysis.runAuto(props.id)
    ElMessage.success(`${analysis.blocks.length} StatBlock`)
  } catch (e) {
    handleApiError(e)
  }
}

async function onOpen(id: string): Promise<void> {
  await analysis.loadOne(props.id, id)
  drawerOpen.value = true
}

async function onDelete(id: string): Promise<void> {
  if (!await confirmAction(t('common.delete'),
                            { type: 'warning', danger: true,
                              resource_name: 'StatBlock' })) return
  try {
    await analysis.remove(props.id, id)
    ElMessage.success(t('common.ok'))
  } catch (e) { handleApiError(e) }
}

function onManualSubmit(): void {
  manualOpen.value = false
  void analysis.refresh(props.id)
}

function fmtDate(s: string): string {
  try { return new Date(s).toLocaleString() } catch { return s }
}
</script>

<template>
  <div class="analyze">
    <header class="bar">
      <div class="left">
        <h2>临床统计分析</h2>
        <el-tag size="small" type="info">M3</el-tag>
      </div>
      <div class="right">
        <el-button type="primary" @click="onAuto" :loading="analysis.autoRunning">
          自动分析（基于已清洗数据）
        </el-button>
        <el-button @click="manualOpen = true">手动新增分析</el-button>
        <el-dropdown trigger="click" @command="(c: any) => openAdvanced(c)">
          <el-button>高级分析<el-icon class="el-icon--right">▾</el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="multitest">多重比较校正</el-dropdown-item>
              <el-dropdown-item command="subgroup">亚组分析（森林图）</el-dropdown-item>
              <el-dropdown-item command="sensitivity">敏感性分析（ITT/PP/LOCF/MMRM）</el-dropdown-item>
              <el-dropdown-item command="consort">CONSORT 流程</el-dropdown-item>
              <el-dropdown-item command="baseline_balance">基线平衡 SMD</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <section class="content">
      <div v-if="analysis.loading" class="empty">{{ $t('common.loading') }}</div>
      <EmptyState v-else-if="!sortedBlocks.length"
                   icon="📊"
                   :title="$t('analyze.empty_title')"
                   :description="$t('analyze.empty_desc')"
                   :cta-text="$t('analyze.auto_run')"
                   @cta="onAuto" />
      <el-table v-else :data="sortedBlocks" stripe size="default" class="stat-table">
        <el-table-column prop="title" label="标题" min-width="320">
          <template #default="{ row }">
            <a class="link" @click="onOpen(row.id)">{{ row.title }}</a>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="(typeColor[row.analysis_type] as any) || ''" size="small">
              {{ typeLabel[row.analysis_type] || row.analysis_type }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="样本量" width="100">
          <template #default="{ row }">
            <span v-if="row.n_rows != null">{{ row.n_rows }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="来源文件" min-width="240">
          <template #default="{ row }">
            <span class="src" v-for="s in row.source_files" :key="s">
              {{ s.split(/[\\\/]/).pop() }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ fmtDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="onOpen(row.id)">查看</el-button>
            <el-button size="small" type="danger" plain @click="onDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <DataAskPanel :project-id="props.id" @stat-block-saved="analysis.refresh(props.id)" />

    <StatBlockDrawer v-model:open="drawerOpen" :block="analysis.selected" />
    <ManualAnalysisDialog v-model:open="manualOpen" :project-id="props.id"
                          @submitted="onManualSubmit" />
    <AdvancedAnalysisDialog v-model:open="advancedOpen" :project-id="props.id"
                             :kind="advancedKind"
                             @done="analysis.refresh(props.id)" />
  </div>
</template>

<style scoped>
.analyze {
  display: flex; flex-direction: column;
  height: calc(100vh - 56px);
}
.bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 28px; background: #fff; border-bottom: 1px solid #e5e7eb;
}
.bar .left { display: flex; align-items: center; gap: 12px; }
.bar h2 { margin: 0; font-size: 18px; color: #111827; font-weight: 600; }
.content { flex: 1; padding: 18px 28px; overflow: auto; }
.empty { color: #6b7280; padding: 80px 0; text-align: center; }
.stat-table .link { color: #1d4ed8; cursor: pointer; }
.stat-table .link:hover { text-decoration: underline; }
.src { display: inline-block; margin-right: 10px; color: #4b5563; font-size: 12px; }
.muted { color: #9ca3af; }
@media (max-width: 767px) {
  .analyze { height: calc(100dvh - 48px); font-size: 14px; }
  .bar { flex-direction: column; align-items: flex-start; gap: 8px; padding: 10px 12px; }
  .bar .right { width: 100%; display: flex; flex-wrap: wrap; gap: 6px; }
  .content { padding: 8px 10px; }
  .stat-table :deep(.el-table__cell) { padding: 6px 4px; }
}
</style>
