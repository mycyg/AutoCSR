<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listAuditEvents, listSignatures, verifyAuditChain, verifySignature,
  type AuditEventDTO, type AuditChainResultDTO, type SignatureDTO,
} from '@/api/rest'

const props = defineProps<{ id: string }>()

const events = ref<AuditEventDTO[]>([])
const chain = ref<AuditChainResultDTO | null>(null)
const signatures = ref<SignatureDTO[]>([])
const filters = ref({ actor: '', action: '', resource_type: '' })
const loading = ref(false)
const verifying = ref(false)
const sigVerifyCache = ref<Record<string, boolean>>({})

async function refresh(): Promise<void> {
  loading.value = true
  try {
    events.value = await listAuditEvents(props.id, { ...filters.value, limit: 500 })
    chain.value = await verifyAuditChain(props.id)
    signatures.value = await listSignatures(props.id)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    loading.value = false
  }
}

async function reverify(): Promise<void> {
  verifying.value = true
  try {
    chain.value = await verifyAuditChain(props.id)
    ElMessage.success(chain.value.verified ? '链完整' : `链断裂于 ${chain.value.broken_at}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    verifying.value = false
  }
}

async function verifySig(sig: SignatureDTO): Promise<void> {
  try {
    const r = await verifySignature(props.id, sig.id)
    sigVerifyCache.value[sig.id] = r.verified
    ElMessage.success(`${sig.id}: ${r.verified ? '验证通过' : '验证失败'}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  }
}

onMounted(() => { void refresh() })

const actors = computed(() => Array.from(new Set(events.value.map(e => e.actor))).filter(Boolean))
const resourceTypes = computed(() => Array.from(new Set(events.value.map(e => e.resource_type))).filter(Boolean))
</script>

<template>
  <div class="audit-view">
    <div class="topbar">
      <h2>审计跟踪</h2>
      <span class="badge" :class="{ ok: chain?.verified, bad: chain && !chain.verified }">
        <el-tag :type="chain?.verified ? 'success' : 'danger'" size="small">
          {{ chain?.verified ? `Hash 链完整 (${chain.total})` : `链断裂@${chain?.broken_at}` }}
        </el-tag>
      </span>
      <el-button size="small" :loading="verifying" @click="reverify">重新 verify</el-button>
      <el-button size="small" @click="refresh">刷新</el-button>
    </div>

    <el-row :gutter="12" class="filters">
      <el-col :span="6">
        <el-select v-model="filters.actor" placeholder="actor" clearable size="small">
          <el-option v-for="a in actors" :key="a" :label="a" :value="a" />
        </el-select>
      </el-col>
      <el-col :span="6">
        <el-input v-model="filters.action" placeholder="action 关键字" clearable size="small" />
      </el-col>
      <el-col :span="6">
        <el-select v-model="filters.resource_type" placeholder="resource_type" clearable size="small">
          <el-option v-for="r in resourceTypes" :key="r" :label="r" :value="r" />
        </el-select>
      </el-col>
      <el-col :span="6">
        <el-button type="primary" size="small" @click="refresh">应用过滤</el-button>
      </el-col>
    </el-row>

    <el-tabs>
      <el-tab-pane label="事件时间线">
        <el-table :data="events" stripe size="small" :max-height="500" v-loading="loading">
          <el-table-column prop="ts" label="ts" width="200" />
          <el-table-column prop="actor" label="actor" width="140" />
          <el-table-column prop="action" label="action" />
          <el-table-column prop="resource_type" label="resource" width="120" />
          <el-table-column prop="reason" label="reason" width="200" />
          <el-table-column label="hash" width="120">
            <template #default="{ row }">
              <code class="hash">{{ (row.curr_event_hash || '').slice(0, 8) }}</code>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane :label="`电子签名 (${signatures.length})`">
        <el-table :data="signatures" stripe size="small" :max-height="500">
          <el-table-column prop="id" label="id" width="170" />
          <el-table-column prop="signer" label="signer" width="160" />
          <el-table-column prop="reason" label="reason" />
          <el-table-column prop="signed_artifact_type" label="artifact_type" width="130" />
          <el-table-column prop="signed_artifact_id" label="artifact_id" />
          <el-table-column prop="algorithm" label="algo" width="120" />
          <el-table-column label="verify" width="120">
            <template #default="{ row }">
              <el-button v-if="sigVerifyCache[row.id] === undefined" size="small" @click="verifySig(row)">verify</el-button>
              <el-tag v-else :type="sigVerifyCache[row.id] ? 'success' : 'danger'" size="small">
                {{ sigVerifyCache[row.id] ? 'OK' : 'FAIL' }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.audit-view { padding: 16px; }
.topbar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.filters { margin-bottom: 12px; }
.hash { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; color: #6b7280; }
</style>
