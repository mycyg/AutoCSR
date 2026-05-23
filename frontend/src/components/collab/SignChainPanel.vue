<script setup lang="ts">
/**
 * Sign-chain UI (M17).
 *
 * Visual flow: statistician → medical → regulatory → approver
 *
 * - Shows each step + status (pending / signed / skipped).
 * - "Advance my step" button posts to /sign_chain/advance with the
 *   user's role + signer id (taken from props or current user).
 * - "Init chain" lazy-creates the default chain when none exists.
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  advanceSignChain, getSignChain, initSignChain,
  whoami, type SignChainDTO, type UserDTO,
} from '@/api/rest'
import { handleApiError } from '@/utils/errors'
import { useConfirm } from '@/composables/useConfirm'

const props = defineProps<{ projectId: string; taskId: string }>()
const { t } = useI18n()
const { confirmAction } = useConfirm()

const chain = ref<SignChainDTO | null>(null)
const me = ref<UserDTO | null>(null)
const loading = ref(false)
const advancing = ref(false)
const reason = ref('')

async function refresh(): Promise<void> {
  loading.value = true
  try {
    chain.value = await getSignChain(props.projectId, props.taskId)
  } catch (e: any) {
    if (e?.response?.status === 404) {
      chain.value = null  // not initialised yet
    } else {
      handleApiError(e)
    }
  } finally { loading.value = false }
}

async function loadMe(): Promise<void> {
  try { me.value = await whoami() } catch { /* ignore */ }
}

async function onInit(): Promise<void> {
  if (!await confirmAction(t('sign_chain.init_confirm'),
                            { type: 'info', confirm_text: 'sign_chain.init' })) return
  try {
    chain.value = await initSignChain(props.projectId, props.taskId)
  } catch (e) {
    handleApiError(e)
  }
}

function myRoleMatches(role: string): boolean {
  if (!me.value) return false
  // Backend uses singular role; admins can always advance.
  if (me.value.role === 'admin') return true
  // Loose match: "statistician" / "medical" / "regulatory" / "approver"
  // — author/reviewer/approver are the schema roles, so accept either.
  return me.value.role === role || role.includes(me.value.role)
}

const canAdvance = computed(() => {
  if (!chain.value || !me.value || !chain.value.current_step) return false
  return myRoleMatches(chain.value.current_step)
})

async function onAdvance(): Promise<void> {
  if (!chain.value?.current_step || !me.value) return
  const role = chain.value.current_step
  if (!await confirmAction(t('sign_chain.advance_confirm', { role }),
                            { type: 'warning', confirm_text: 'sign_chain.advance' })) return
  advancing.value = true
  try {
    await advanceSignChain(props.projectId, props.taskId, {
      role, signer_user_id: me.value.id, reason: reason.value,
    })
    reason.value = ''
    await refresh()
  } catch (e) {
    handleApiError(e)
  } finally { advancing.value = false }
}

onMounted(async () => {
  await loadMe()
  await refresh()
})

watch(() => props.taskId, () => refresh())

function stepIcon(status: string): string {
  if (status === 'signed') return '✓'
  if (status === 'skipped') return '–'
  return '○'
}
</script>

<template>
  <div class="sign-chain-panel">
    <header>
      <h4>{{ t('sign_chain.title') }}</h4>
      <el-button v-if="!chain" size="small" type="primary"
                 :loading="loading" @click="onInit">
        {{ t('sign_chain.init') }}
      </el-button>
      <el-button v-else link size="small" :aria-label="t('common.refresh')" @click="refresh">
        ↻
      </el-button>
    </header>

    <div v-if="!chain && !loading" class="muted">
      {{ t('sign_chain.empty') }}
    </div>

    <div v-if="chain" class="flow" role="list">
      <div v-for="(s, i) in chain.steps" :key="s.role + i" role="listitem"
           class="step" :class="s.status"
           :aria-current="s.role === chain.current_step ? 'step' : undefined">
        <div class="badge" :title="s.status">{{ stepIcon(s.status) }}</div>
        <div class="body">
          <div class="role">{{ s.role }}</div>
          <div v-if="s.signer_user_id" class="signer">@{{ s.signer_user_id }}</div>
          <div v-if="s.signed_at" class="ts">
            {{ new Date(s.signed_at).toLocaleString() }}
          </div>
          <div v-if="s.reason" class="reason">{{ s.reason }}</div>
        </div>
      </div>
    </div>

    <div v-if="chain && !chain.completed" class="advance-row">
      <el-input v-model="reason" type="textarea" :rows="2" size="small"
                :placeholder="t('sign_chain.reason_placeholder')" />
      <el-button :disabled="!canAdvance" :loading="advancing"
                 type="primary" size="small" @click="onAdvance">
        {{ t('sign_chain.advance') }}
      </el-button>
      <div v-if="!canAdvance && chain.current_step" class="muted hint">
        {{ t('sign_chain.not_your_turn', { role: chain.current_step }) }}
      </div>
    </div>

    <div v-if="chain?.completed" class="completed">
      ✓ {{ t('sign_chain.completed') }}
    </div>
  </div>
</template>

<style scoped>
.sign-chain-panel {
  padding: 12px;
  background: var(--color-surface);
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
header h4 {
  margin: 0;
  font-size: var(--font-size-md);
  color: var(--color-text-strong);
  font-weight: 600;
}
.flow {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}
.step {
  display: flex;
  gap: 10px;
  padding: 8px;
  border-radius: var(--radius-sm);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border);
}
.step.signed  { border-left: 3px solid var(--color-success); }
.step.pending { border-left: 3px solid var(--color-border-strong); }
.step.skipped { opacity: 0.55; border-left: 3px solid var(--color-warn); }
.step[aria-current="step"] {
  border-left: 3px solid var(--color-primary);
  background: var(--color-primary-soft);
}
.badge {
  width: 22px; height: 22px;
  border-radius: 50%;
  background: var(--color-surface-3);
  display: flex; align-items: center; justify-content: center;
  font-family: ui-monospace, monospace;
  color: var(--color-text-mute);
  flex: 0 0 22px;
}
.step.signed .badge { background: var(--color-success); color: #fff; }
.step.pending[aria-current="step"] .badge { background: var(--color-primary); color: #fff; }
.body { flex: 1; }
.role {
  font-weight: 600;
  font-size: var(--font-size-md);
  color: var(--color-text-strong);
}
.signer, .ts, .reason {
  font-size: var(--font-size-xs);
  color: var(--color-text-mute);
}
.reason { margin-top: 4px; }
.advance-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.advance-row .hint { font-size: var(--font-size-xs); }
.completed {
  padding: 10px;
  text-align: center;
  color: var(--color-success);
  font-weight: 600;
  background: var(--color-surface-2);
  border-radius: var(--radius-sm);
}
.muted { color: var(--color-text-mute); font-size: var(--font-size-sm); }
</style>
