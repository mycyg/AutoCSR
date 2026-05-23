<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useShortcuts } from '@/composables/useShortcuts'
import { useOutlineStore } from '@/stores/outline'
import { useReportStore } from '@/stores/report'
import { useI18n } from 'vue-i18n'

interface Hit {
  kind: 'section' | 'stat'
  label: string
  hint?: string
  href: string
}

const route = useRoute()
const router = useRouter()
const outlineStore = useOutlineStore()
const reportStore = useReportStore()
const { t } = useI18n()

const visible = ref(false)
const q = ref('')
const inputRef = ref<HTMLInputElement | null>(null)

const projectId = computed(() => (route.params.id as string | undefined) || '')

const allHits = computed<Hit[]>(() => {
  const pid = projectId.value
  if (!pid) return []
  const out: Hit[] = []
  // Outline section titles — walk the tree
  const outline = outlineStore.outline
  if (outline && Array.isArray(outline.root_sections)) {
    const walk = (n: { id: string; title: string; children?: any[] }): void => {
      out.push({
        kind: 'section',
        label: `${n.id}  ${n.title}`,
        hint: t('search.section'),
        href: `/p/${pid}/report?node=${encodeURIComponent(n.id)}`,
      })
      for (const c of n.children || []) walk(c)
    }
    for (const root of outline.root_sections) walk(root)
  }
  // Section drafts as a fallback for projects without an outline yet
  if (!out.length && Array.isArray(reportStore.drafts)) {
    for (const d of reportStore.drafts) {
      out.push({
        kind: 'section',
        label: `${d.node_id}`,
        hint: t('search.section'),
        href: `/p/${pid}/report?node=${encodeURIComponent(d.node_id)}`,
      })
    }
  }
  return out
})

const filtered = computed<Hit[]>(() => {
  const term = q.value.trim().toLowerCase()
  if (!term) return allHits.value.slice(0, 30)
  return allHits.value.filter(h => h.label.toLowerCase().includes(term)).slice(0, 30)
})

useShortcuts({ search: () => { visible.value = true } })

watch(visible, async (v) => {
  if (v) {
    q.value = ''
    await nextTick()
    inputRef.value?.focus()
  }
})

function pick(h: Hit): void {
  visible.value = false
  router.push(h.href)
}

function onEnter(): void {
  if (filtered.value.length > 0) pick(filtered.value[0])
}
</script>

<template>
  <el-dialog v-model="visible" :title="$t('search.title')" width="560" align-center>
    <el-input
      ref="inputRef"
      v-model="q"
      :placeholder="$t('search.placeholder')"
      autofocus
      clearable
      @keyup.enter="onEnter"
    />
    <ul class="hits">
      <li v-for="h in filtered" :key="h.kind + ':' + h.href" @click="pick(h)">
        <span class="kind">{{ h.hint }}</span>
        <span class="label">{{ h.label }}</span>
      </li>
      <li v-if="!filtered.length" class="empty">{{ $t('search.empty') }}</li>
    </ul>
  </el-dialog>
</template>

<style scoped>
.hits {
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
  max-height: 320px;
  overflow-y: auto;
}
.hits li {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  color: #1f2937;
  font-size: 13px;
}
.hits li:hover { background: #f3f4f6; }
.hits li.empty { color: #9ca3af; cursor: default; font-size: 12px; padding: 12px 4px; }
.hits li.empty:hover { background: transparent; }
.kind {
  font-size: 11px;
  color: #6b7280;
  background: #f3f4f6;
  padding: 1px 6px;
  border-radius: 4px;
  flex: 0 0 auto;
}
.label { flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
</style>
