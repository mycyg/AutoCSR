<template>
  <div class="dashboard-page">
    <header>
      <h1>Dashboards · {{ pid }}</h1>
      <el-button type="primary" :icon="Plus" @click="onCreate" :disabled="!availableStats.length">
        New dashboard
      </el-button>
    </header>

    <el-empty v-if="!dashboards.length && !loading" description="No dashboards yet. Build one from your analysis blocks." />
    <el-skeleton v-if="loading" :rows="6" animated />

    <div v-for="d in dashboards" :key="d.id" class="dashboard-card">
      <div class="dash-head">
        <h3>{{ d.name }}</h3>
        <el-button text type="danger" size="small" @click="onDelete(d)">Delete</el-button>
      </div>
      <div class="dash-grid">
        <div v-for="(cell, idx) in d.layout" :key="cell.cell_id || idx"
              class="dash-cell"
              :style="cellStyle(cell)">
          <h4>{{ cellTitle(cell) }}</h4>
          <component v-if="cellComponent(cell)"
                      :is="cellComponent(cell)!.comp"
                      :result-json="cellComponent(cell)!.rj" />
          <div v-else class="dash-cell-empty">
            Stat block {{ cell.stat_id }} not loaded.
          </div>
        </div>
      </div>
    </div>

    <!-- Create dialog -->
    <el-dialog v-model="createOpen" title="Compose a dashboard" width="640px">
      <el-form label-position="top" :model="form">
        <el-form-item label="Dashboard name">
          <el-input v-model="form.name" placeholder="Eg. KOL summary" />
        </el-form-item>
        <el-form-item label="Pick analysis blocks">
          <el-checkbox-group v-model="form.statIds">
            <el-checkbox v-for="s in availableStats" :key="s.id" :label="s.id">
              {{ s.title }} <span class="muted">({{ s.analysis_type }})</span>
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createOpen = false">Cancel</el-button>
        <el-button type="primary" :loading="creating" @click="doCreate"
                    :disabled="!form.statIds.length || !form.name">
          Create
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createDashboard, deleteDashboard, getStat, listDashboards, listStats,
  type DashboardCellDTO, type DashboardConfigDTO, type StatBlockDTO,
  type StatBlockSummaryDTO,
} from '@/api/rest'
import KMWithRiskChart from '@/components/analysis/KMWithRiskChart.vue'
import BlandAltmanChart from '@/components/analysis/BlandAltmanChart.vue'
import HeatmapChart from '@/components/analysis/HeatmapChart.vue'
import PKProfile3D from '@/components/analysis/PKProfile3D.vue'

const props = defineProps<{ id: string }>()
const pid = computed(() => props.id)

const dashboards = ref<DashboardConfigDTO[]>([])
const availableStats = ref<StatBlockSummaryDTO[]>([])
const loaded = reactive<Record<string, StatBlockDTO>>({})
const loading = ref(false)

const createOpen = ref(false)
const creating = ref(false)
const form = reactive<{ name: string; statIds: string[] }>({ name: '', statIds: [] })

function cellStyle(cell: DashboardCellDTO) {
  const w = cell.position?.w || 6
  const h = cell.position?.h || 4
  return {
    gridColumn: `span ${w}`,
    minHeight: `${h * 60}px`,
  }
}

function cellTitle(cell: DashboardCellDTO): string {
  const sb = loaded[cell.stat_id]
  return cell.title || sb?.title || cell.stat_id
}

function cellComponent(cell: DashboardCellDTO):
    { comp: any; rj: Record<string, any> } | null {
  const sb = loaded[cell.stat_id]
  if (!sb) return null
  const rj = (sb.result_json || {}) as Record<string, any>
  const spec = rj.echarts_spec || {}
  const t = spec.type || sb.analysis_type
  if (t === 'km_with_risk' || sb.analysis_type === 'survival') return { comp: KMWithRiskChart, rj }
  if (t === 'bland_altman') return { comp: BlandAltmanChart, rj }
  if (t === 'heatmap') return { comp: HeatmapChart, rj }
  if (t === 'scatter3D' || t === 'pk_3d') return { comp: PKProfile3D, rj }
  return null
}

async function loadAll() {
  loading.value = true
  try {
    dashboards.value = await listDashboards(pid.value)
    availableStats.value = await listStats(pid.value)
    // hydrate stat blocks referenced by any dashboard cell
    const ids = new Set<string>()
    for (const d of dashboards.value) {
      for (const c of d.layout) ids.add(c.stat_id)
    }
    for (const id of ids) {
      try {
        loaded[id] = await getStat(pid.value, id)
      } catch { /* ignore */ }
    }
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'Failed to load dashboards')
  } finally {
    loading.value = false
  }
}

function onCreate() {
  form.name = ''
  form.statIds = []
  createOpen.value = true
}

async function doCreate() {
  creating.value = true
  try {
    const layout: DashboardCellDTO[] = form.statIds.map((sid, i) => ({
      stat_id: sid, chart_type: 'auto',
      position: { x: (i % 2) * 6, y: Math.floor(i / 2) * 4, w: 6, h: 5 },
    }))
    const d = await createDashboard(pid.value, form.name, layout)
    dashboards.value = [d, ...dashboards.value]
    for (const c of layout) {
      try { loaded[c.stat_id] = await getStat(pid.value, c.stat_id) } catch {}
    }
    createOpen.value = false
    ElMessage.success('Dashboard created')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'Create failed')
  } finally {
    creating.value = false
  }
}

async function onDelete(d: DashboardConfigDTO) {
  try {
    await ElMessageBox.confirm(`Delete dashboard "${d.name}"?`, 'Confirm', { type: 'warning' })
  } catch { return }
  try {
    await deleteDashboard(pid.value, d.id)
    dashboards.value = dashboards.value.filter(x => x.id !== d.id)
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'Delete failed')
  }
}

onMounted(loadAll)
</script>

<style scoped>
.dashboard-page {
  max-width: 1280px;
  margin: 0 auto;
  padding: 24px;
}
header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}
header h1 {
  margin: 0;
  font-size: 22px;
  color: #1f2937;
}
.dashboard-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.dash-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.dash-head h3 {
  margin: 0;
  font-size: 16px;
  color: #1f2937;
}
.dash-grid {
  display: grid;
  grid-template-columns: repeat(12, 1fr);
  gap: 14px;
}
.dash-cell {
  background: #f9fafb;
  border-radius: 6px;
  padding: 12px;
  border: 1px solid #e5e7eb;
}
.dash-cell h4 {
  margin: 0 0 12px;
  font-size: 13px;
  color: #374151;
}
.dash-cell-empty {
  text-align: center;
  color: #9ca3af;
  padding: 24px;
  font-size: 12px;
}
.muted {
  color: #9ca3af;
  font-size: 12px;
}
</style>
