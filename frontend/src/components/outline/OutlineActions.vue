<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { OutlineDTO } from '@/api/rest'

const props = defineProps<{ outline: OutlineDTO | null; versions: number[]; building: boolean }>()
const emit = defineEmits<{ (e: 'rebuild'): void; (e: 'restore', v: number): void }>()

const pickedVersion = ref<number | null>(null)

watch(() => props.outline, (o) => {
  if (o) pickedVersion.value = o.version
})

const nodeCount = computed(() => {
  if (!props.outline) return 0
  const stack = [...props.outline.root_sections]
  let c = 0
  while (stack.length) {
    const n = stack.pop()!
    c += 1
    stack.push(...n.children)
  }
  return c
})

const statCount = computed(() => {
  if (!props.outline) return 0
  const stack = [...props.outline.root_sections]
  let c = 0
  while (stack.length) {
    const n = stack.pop()!
    if (n.stat_refs.length) c += 1
    stack.push(...n.children)
  }
  return c
})
</script>

<template>
  <div class="actions">
    <section class="card" v-if="outline">
      <h4>当前大纲</h4>
      <div class="row"><span>版本</span><strong>v{{ outline.version }}</strong></div>
      <div class="row"><span>原则</span><strong>{{ outline.principle_id }}</strong></div>
      <div class="row"><span>节点总数</span><strong>{{ nodeCount }}</strong></div>
      <div class="row"><span>含 stat 节</span><strong>{{ statCount }}</strong></div>
    </section>

    <section class="card">
      <h4>历史版本</h4>
      <el-select v-model="pickedVersion" size="small" placeholder="选择版本" style="width: 100%">
        <el-option v-for="v in versions" :key="v" :value="v" :label="`v${v}`" />
      </el-select>
      <el-button size="small" style="margin-top: 8px"
                 :disabled="!pickedVersion || pickedVersion === outline?.version"
                 @click="pickedVersion && emit('restore', pickedVersion)">
        回滚到该版本
      </el-button>
    </section>

    <section class="card">
      <el-button type="primary" size="small" :loading="building" @click="emit('rebuild')">
        重新生成大纲
      </el-button>
      <el-tooltip content="M4 阶段启用" placement="top">
        <el-button size="small" style="margin-top: 8px" disabled>
          跳转到撰写
        </el-button>
      </el-tooltip>
    </section>
  </div>
</template>

<style scoped>
.actions { display: flex; flex-direction: column; gap: 12px; }
.card {
  background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px;
  padding: 10px 12px;
}
.card h4 { margin: 0 0 8px 0; font-size: 12px; color: #374151; }
.row { display: flex; justify-content: space-between; font-size: 12px; color: #4b5563; margin: 3px 0; }
.row strong { color: #111827; }
</style>
