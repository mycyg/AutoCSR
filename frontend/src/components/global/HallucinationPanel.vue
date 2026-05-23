<script setup lang="ts">
/**
 * Hallucination Check (M17 frontend wiring).
 *
 * Triggers /hallucination_check and shows findings grouped by section.
 * The parent component decides where to mount this (a tab in ReviewView).
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import {
  getHallucinationCheck, runHallucinationCheck,
  type HallucinationFindingDTO, type HallucinationResultDTO,
} from '@/api/rest'
import { handleApiError } from '@/utils/errors'

const props = defineProps<{ projectId: string }>()
const { t } = useI18n()
const router = useRouter()

const data = ref<HallucinationResultDTO | null>(null)
const running = ref(false)

async function refresh(): Promise<void> {
  try { data.value = await getHallucinationCheck(props.projectId) }
  catch { data.value = null }
}
async function run(): Promise<void> {
  running.value = true
  try {
    data.value = await runHallucinationCheck(props.projectId)
  } catch (e) {
    handleApiError(e)
  } finally { running.value = false }
}

onMounted(refresh)

const bySection = computed(() => {
  const out: Record<string, HallucinationFindingDTO[]> = {}
  for (const f of data.value?.findings || []) {
    const k = f.node_id || '_'
    if (!out[k]) out[k] = []
    out[k].push(f)
  }
  return out
})

function goto(nodeId: string): void {
  router.push(`/p/${props.projectId}/report?node=${encodeURIComponent(nodeId)}`)
}

function sevType(sev: string): string {
  if (sev === 'error') return 'danger'
  if (sev === 'warn') return 'warning'
  return 'info'
}
</script>

<template>
  <div class="hallucination-panel">
    <header>
      <h4>{{ t('hallucination.title') }}</h4>
      <el-tag v-if="data" size="small" :type="data.n_findings ? 'danger' : 'success'">
        {{ data.n_findings }} {{ t('hallucination.n_findings') }}
      </el-tag>
      <el-button size="small" type="primary" plain :loading="running" @click="run">
        {{ t('hallucination.run') }}
      </el-button>
    </header>

    <p v-if="!data" class="muted">{{ t('hallucination.never_run') }}</p>
    <p v-else-if="!data.n_findings" class="ok">
      ✓ {{ t('hallucination.no_findings') }}
    </p>

    <div v-else class="groups">
      <div v-for="(items, nodeId) in bySection" :key="nodeId" class="group">
        <div class="group-head">
          <a class="link" @click="goto(nodeId)">§ {{ nodeId }}</a>
          <el-tag size="small">{{ items.length }}</el-tag>
        </div>
        <div v-for="(f, i) in items" :key="i" class="finding">
          <el-tag size="small" :type="sevType(f.severity)">{{ f.severity }}</el-tag>
          <span v-if="f.ref_code" class="code">{{ f.ref_code }}</span>
          <span class="reason">{{ f.reason }}</span>
          <div v-if="f.text_excerpt" class="excerpt">"{{ f.text_excerpt }}"</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.hallucination-panel { padding: 12px 16px; }
header {
  display: flex; align-items: center; gap: 8px;
  margin-bottom: 12px;
}
header h4 {
  margin: 0; font-size: var(--font-size-lg);
  color: var(--color-text-strong); font-weight: 600;
}
header .el-button { margin-left: auto; }
.muted { color: var(--color-text-mute); font-size: var(--font-size-sm); }
.ok { color: var(--color-success); font-weight: 600; padding: 24px 0; text-align: center; }
.groups { display: flex; flex-direction: column; gap: 12px; }
.group {
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  padding: 8px 12px;
}
.group-head {
  display: flex; gap: 8px; align-items: center;
  margin-bottom: 6px;
}
.link {
  color: var(--color-primary);
  font-weight: 600;
  cursor: pointer;
}
.link:hover { text-decoration: underline; }
.finding {
  padding: 6px 0;
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: var(--font-size-sm);
}
.finding:first-of-type { border-top: none; }
.finding .code {
  font-family: ui-monospace, monospace;
  background: var(--color-surface-3);
  padding: 0 4px;
  border-radius: 3px;
}
.finding .reason { flex: 1; min-width: 200px; color: var(--color-text); }
.finding .excerpt {
  width: 100%;
  font-style: italic;
  color: var(--color-text-mute);
  padding: 4px 8px;
  border-left: 2px solid var(--color-warn);
  margin-top: 2px;
}
</style>
