<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

const props = defineProps<{ terms: Record<string, string> }>()
const emit = defineEmits<{ (e: 'save', terms: Record<string, string>): Promise<void> | void }>()

interface Row { id: number; key: string; value: string }

const rows = ref<Row[]>([])
let nextId = 0

watch(() => props.terms, (t) => {
  rows.value = Object.entries(t || {}).map(([k, v]) => ({ id: nextId++, key: k, value: v }))
}, { immediate: true })

const dirty = computed(() => {
  const current = Object.fromEntries(rows.value.filter((r) => r.key.trim()).map((r) => [r.key.trim(), r.value]))
  return JSON.stringify(current) !== JSON.stringify(props.terms)
})

function add(): void {
  rows.value.push({ id: nextId++, key: '', value: '' })
}
function remove(id: number): void {
  rows.value = rows.value.filter((r) => r.id !== id)
}

async function save(): Promise<void> {
  const out: Record<string, string> = {}
  for (const r of rows.value) {
    const k = r.key.trim()
    if (!k) continue
    out[k] = r.value
  }
  await emit('save', out)
  ElMessage.success('术语表已保存')
}
</script>

<template>
  <div class="terminology">
    <div class="header">
      <span class="title">术语对照</span>
      <span class="hint">writer / harmonizer 调用时会注入</span>
    </div>
    <table class="grid">
      <thead>
        <tr><th>英文/原文</th><th>中文/译文</th><th></th></tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="r.id">
          <td><el-input v-model="r.key" size="small" placeholder="key" /></td>
          <td><el-input v-model="r.value" size="small" placeholder="value" /></td>
          <td><el-button text size="small" type="danger" @click="remove(r.id)">×</el-button></td>
        </tr>
        <tr v-if="!rows.length"><td colspan="3" class="empty">空，点 + 添加</td></tr>
      </tbody>
    </table>
    <div class="actions">
      <el-button size="small" plain @click="add">+ 添加</el-button>
      <el-button size="small" type="primary" :disabled="!dirty" @click="save">保存</el-button>
    </div>
  </div>
</template>

<style scoped>
.terminology { display: flex; flex-direction: column; gap: 8px; font-size: 12px; }
.header { display: flex; align-items: baseline; gap: 8px; }
.title { font-weight: 600; color: #1f2937; font-size: 13px; }
.hint { color: #9ca3af; font-size: 11px; }
.grid { width: 100%; border-collapse: collapse; }
.grid th, .grid td { padding: 2px 4px; text-align: left; }
.grid thead th { color: #6b7280; font-weight: 500; font-size: 11px; }
.grid td.empty { color: #9ca3af; text-align: center; padding: 12px 0; }
.actions { display: flex; gap: 6px; justify-content: flex-end; }
</style>
