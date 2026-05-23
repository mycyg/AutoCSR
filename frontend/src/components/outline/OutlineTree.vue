<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { OutlineNodeDTO } from '@/api/rest'
import { useShortcuts } from '@/composables/useShortcuts'

interface ElTreeNode {
  id: string
  label: string
  raw: OutlineNodeDTO
  children?: ElTreeNode[]
}

const props = defineProps<{ nodes: OutlineNodeDTO[]; selectedId: string | null }>()
const emit = defineEmits<{ (e: 'select', id: string): void }>()
const { t } = useI18n()

function toTree(nodes: OutlineNodeDTO[]): ElTreeNode[] {
  return nodes.map((n) => ({
    id: n.id,
    label: n.title,
    raw: n,
    children: n.children?.length ? toTree(n.children) : undefined,
  }))
}

const tree = computed(() => toTree(props.nodes))
const filter = ref('')

function filterMethod(value: string, data: ElTreeNode): boolean {
  if (!value) return true
  return (data.id + ' ' + data.label).toLowerCase().includes(value.toLowerCase())
}

function onClick(node: ElTreeNode): void {
  emit('select', node.id)
}

const statusColor: Record<string, string> = {
  pending: '#9ca3af',
  writing: '#f59e0b',
  done: '#10b981',
  editing: '#3b82f6',
}

interface ElTreeRef {
  filter: (q: string) => void
  store?: { nodesMap: Record<string, { expanded: boolean }> }
  setCurrentKey?: (k: string) => void
}
const treeRef = ref<ElTreeRef | null>(null)
watch(filter, (v) => { treeRef.value?.filter(v) })

/* j/k navigation: keep a flat order of node ids in DOM tree order. */
const flatIds = computed(() => {
  const out: string[] = []
  const walk = (n: OutlineNodeDTO): void => {
    out.push(n.id)
    for (const c of n.children || []) walk(c)
  }
  for (const root of props.nodes) walk(root)
  return out
})

function moveBy(delta: number): void {
  const ids = flatIds.value
  if (!ids.length) return
  const cur = props.selectedId
  let idx = cur ? ids.indexOf(cur) : -1
  idx = Math.max(0, Math.min(ids.length - 1, idx + delta))
  const next = ids[idx]
  emit('select', next)
  nextTick(() => {
    treeRef.value?.setCurrentKey?.(next)
    const el = document.querySelector(`.outline-tree .el-tree-node[data-key="${CSS.escape(next)}"]`)
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  })
}

useShortcuts({
  outline_next: () => moveBy(1),
  outline_prev: () => moveBy(-1),
  list_down: () => moveBy(1),
  list_up: () => moveBy(-1),
})

function collapseAll(): void {
  if (!treeRef.value?.store) return
  for (const k of Object.keys(treeRef.value.store.nodesMap)) {
    treeRef.value.store.nodesMap[k].expanded = false
  }
}
function gotoCurrent(): void {
  if (!props.selectedId) return
  treeRef.value?.setCurrentKey?.(props.selectedId)
  const el = document.querySelector(
    `.outline-tree .el-tree-node[data-key="${CSS.escape(props.selectedId)}"]`)
  el?.scrollIntoView({ block: 'center', behavior: 'smooth' })
}
</script>

<template>
  <div class="outline-tree" role="tree" :aria-label="t('outline.title')">
    <div class="ot-toolbar">
      <el-input v-model="filter" :placeholder="t('outline.search_placeholder')"
                size="small" clearable />
      <el-button size="small" :aria-label="t('outline.collapse_all')"
                  @click="collapseAll" title="Collapse all">⤡</el-button>
      <el-button size="small" :aria-label="t('outline.goto_current')"
                  @click="gotoCurrent" title="Goto current">⊙</el-button>
    </div>
    <el-tree
      ref="treeRef"
      :data="tree"
      node-key="id"
      :default-expanded-keys="['1','2','5','9','10','11','12']"
      :filter-node-method="filterMethod"
      :current-node-key="selectedId || ''"
      highlight-current
      class="tree"
      @node-click="onClick">
      <template #default="{ data }">
        <div class="row" role="treeitem"
              :aria-selected="data.id === selectedId">
          <span class="dot" :style="{ background: statusColor[data.raw.status] }"
                aria-hidden="true"></span>
          <span class="sid">{{ data.id }}</span>
          <span class="title">{{ data.label }}</span>
          <span v-if="data.raw.stat_refs?.length" class="badge stats">
            S{{ data.raw.stat_refs.length }}
          </span>
          <span v-if="data.raw.literature_refs?.length" class="badge lits">
            L{{ data.raw.literature_refs.length }}
          </span>
        </div>
      </template>
    </el-tree>
  </div>
</template>

<style scoped>
.outline-tree { display: flex; flex-direction: column; gap: 8px; height: 100%; }
.ot-toolbar { display: flex; gap: 6px; align-items: center; }
.tree { flex: 1; overflow: auto; font-size: var(--font-size-md); }
.row { display: flex; align-items: center; gap: 6px; padding: 2px 0; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 8px; }
.sid { font-family: ui-monospace, monospace; color: var(--color-text-mute); font-size: var(--font-size-xs); min-width: 50px; }
.title { color: var(--color-text-strong); }
.badge {
  font-size: 10px; padding: 1px 6px; border-radius: 8px;
  font-family: ui-monospace, monospace;
}
.badge.stats { background: #ecfdf5; color: #047857; }
.badge.lits { background: #eff6ff; color: #1d4ed8; }
html[data-theme="dark"] .badge.stats { background: #064e3b; color: #6ee7b7; }
html[data-theme="dark"] .badge.lits { background: #1e3a8a; color: #93c5fd; }
</style>
