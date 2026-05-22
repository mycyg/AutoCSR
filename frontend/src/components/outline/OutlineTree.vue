<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { OutlineNodeDTO } from '@/api/rest'

interface ElTreeNode {
  id: string
  label: string
  raw: OutlineNodeDTO
  children?: ElTreeNode[]
}

const props = defineProps<{ nodes: OutlineNodeDTO[]; selectedId: string | null }>()
const emit = defineEmits<{ (e: 'select', id: string): void }>()

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

const treeRef = ref<{ filter: (q: string) => void } | null>(null)
watch(filter, (v) => { treeRef.value?.filter(v) })
</script>

<template>
  <div class="outline-tree">
    <el-input v-model="filter" placeholder="筛选 id 或标题" size="small" clearable />
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
        <div class="row">
          <span class="dot" :style="{ background: statusColor[data.raw.status] }"></span>
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
.tree { flex: 1; overflow: auto; font-size: 13px; }
.row { display: flex; align-items: center; gap: 6px; padding: 2px 0; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 8px; }
.sid { font-family: ui-monospace, monospace; color: #6b7280; font-size: 11px; min-width: 50px; }
.title { color: #111827; }
.badge {
  font-size: 10px; padding: 1px 6px; border-radius: 8px;
  font-family: ui-monospace, monospace;
}
.badge.stats { background: #ecfdf5; color: #047857; }
.badge.lits { background: #eff6ff; color: #1d4ed8; }
</style>
