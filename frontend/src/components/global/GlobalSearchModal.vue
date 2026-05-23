<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useShortcuts } from '@/composables/useShortcuts'
import { searchProject, type SearchHitDTO } from '@/api/rest'
import { useI18n } from 'vue-i18n'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const RECENT_KEY = 'autocsr_recent_searches'
const MAX_RECENT = 5
const visible = ref(false)
const q = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
const recent = ref<string[]>(loadRecent())
const hits = ref<SearchHitDTO[]>([])
const loading = ref(false)
const selected = ref(0)
let timer: number | null = null
let seq = 0

const projectId = computed(() => (route.params.id as string | undefined) || '')

function loadRecent(): string[] {
  try {
    const raw = window.localStorage.getItem(RECENT_KEY)
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr.slice(0, MAX_RECENT) : []
  } catch { return [] }
}

function saveRecent(term: string): void {
  const cleaned = term.trim()
  if (!cleaned) return
  const next = [cleaned, ...recent.value.filter(x => x !== cleaned)].slice(0, MAX_RECENT)
  recent.value = next
  try { window.localStorage.setItem(RECENT_KEY, JSON.stringify(next)) } catch { /* ignore */ }
}

function hitLabel(hit: SearchHitDTO): string {
  const map: Record<string, string> = {
    section: t('search.section'),
    draft: t('search.draft'),
    stat: t('search.stat'),
    task: t('search.task'),
    review: t('search.review'),
    export: t('search.export'),
  }
  return map[hit.type] || hit.type
}

async function runSearch(term = q.value): Promise<void> {
  const pid = projectId.value
  if (!pid) {
    hits.value = []
    return
  }
  const mySeq = ++seq
  loading.value = true
  try {
    const rows = await searchProject(pid, term, { limit: 40 })
    if (mySeq === seq) {
      hits.value = rows
      selected.value = rows.length ? 0 : -1
    }
  } catch {
    if (mySeq === seq) {
      hits.value = []
      selected.value = -1
    }
  } finally {
    if (mySeq === seq) loading.value = false
  }
}

function scheduleSearch(): void {
  if (timer !== null) window.clearTimeout(timer)
  timer = window.setTimeout(() => void runSearch(), 180)
}

useShortcuts({ search: () => { visible.value = true } })

watch(visible, async (v) => {
  if (v) {
    q.value = ''
    await runSearch('')
    await nextTick()
    inputRef.value?.focus()
  }
})

watch(projectId, () => {
  if (visible.value) void runSearch('')
})

watch(q, scheduleSearch)

function pick(hit?: SearchHitDTO): void {
  const target = hit || hits.value[selected.value]
  if (!target) return
  saveRecent(q.value || target.title)
  visible.value = false
  router.push(target.href)
}

async function confirmPick(): Promise<void> {
  if (timer !== null) {
    window.clearTimeout(timer)
    timer = null
  }
  if (loading.value || !hits.value.length) {
    await runSearch(q.value)
  }
  pick()
}

function move(delta: number): void {
  if (!hits.value.length) return
  selected.value = (selected.value + delta + hits.value.length) % hits.value.length
}

function useRecent(term: string): void {
  q.value = term
  void runSearch(term)
  inputRef.value?.focus()
}
</script>

<template>
  <el-dialog v-model="visible" :title="$t('search.title')" width="680" class="search-dialog" align-center>
    <el-input
      ref="inputRef"
      v-model="q"
      :placeholder="$t('search.placeholder')"
      autofocus
      clearable
      @keydown.down.prevent="move(1)"
      @keydown.up.prevent="move(-1)"
      @keydown.enter.prevent="confirmPick"
    />

    <div class="hits" role="listbox" :aria-label="$t('search.title')">
      <button v-for="(h, i) in hits"
              :key="h.id"
              type="button"
              class="hit"
              :class="{ active: i === selected, [h.severity || '']: !!h.severity }"
              role="option"
              :aria-selected="i === selected"
              @mouseenter="selected = i"
              @click="pick(h)">
        <span class="kind">{{ hitLabel(h) }}</span>
        <span class="main">
          <strong>{{ h.title }}</strong>
          <small>{{ h.snippet }}</small>
        </span>
        <span v-if="h.node_id" class="node">{{ h.node_id }}</span>
      </button>
      <div v-if="loading" class="state">{{ $t('common.loading') }}</div>
      <div v-else-if="!hits.length" class="state">{{ $t('search.empty') }}</div>
    </div>

    <div v-if="!q && recent.length" class="recent">
      <div class="rh">{{ $t('search.recent') }}</div>
      <button v-for="r in recent" :key="r" type="button" class="rterm" @click="useRecent(r)">
        {{ r }}
      </button>
    </div>
  </el-dialog>
</template>

<style scoped>
:deep(.search-dialog) {
  width: min(680px, calc(100vw - 24px));
}
.hits {
  margin: 12px 0 0;
  max-height: min(420px, 54vh);
  overflow-y: auto;
  display: grid;
  gap: 6px;
}
.hit {
  width: 100%;
  min-height: 48px;
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: var(--radius-md);
  border: 1px solid transparent;
  background: transparent;
  color: var(--color-text);
  text-align: left;
  cursor: pointer;
}
.hit:hover,
.hit.active {
  background: var(--color-primary-soft);
  border-color: color-mix(in srgb, var(--color-primary), var(--color-border) 60%);
}
.hit.error { border-left: 3px solid var(--color-error); }
.hit.warn { border-left: 3px solid var(--color-warn); }
.hit.info { border-left: 3px solid var(--color-primary); }
.kind {
  font-size: var(--font-size-xs);
  color: var(--color-primary);
  background: var(--color-surface-3);
  padding: 2px 7px;
  border-radius: 999px;
  font-weight: 700;
}
.main {
  min-width: 0;
  display: grid;
  gap: 2px;
}
.main strong,
.main small,
.node {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.main strong {
  color: var(--color-text-strong);
  font-size: var(--font-size-md);
}
.main small,
.node {
  color: var(--color-text-mute);
  font-size: var(--font-size-xs);
}
.state {
  color: var(--color-text-mute);
  padding: 14px 4px;
  font-size: var(--font-size-sm);
}
.recent {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--color-border);
}
.rh {
  font-size: var(--font-size-xs);
  color: var(--color-text-mute);
  width: 100%;
}
.rterm {
  min-height: 32px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-3);
  border-radius: 999px;
  color: var(--color-text-mute);
  cursor: pointer;
  padding: 4px 10px;
}
.rterm:hover {
  background: var(--color-primary-soft);
  color: var(--color-primary);
}
@media (max-width: 767px) {
  .hit {
    grid-template-columns: 1fr;
    align-items: start;
  }
  .kind,
  .node {
    justify-self: start;
  }
}
</style>
