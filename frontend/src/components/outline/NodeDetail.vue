<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { getStat, type OutlineNodeDTO, type StatBlockDTO } from '@/api/rest'
import StatBlockDrawer from '@/components/analyze/StatBlockDrawer.vue'

const props = defineProps<{ node: OutlineNodeDTO; projectId: string }>()
const emit = defineEmits<{
  (e: 'patch', patch: Record<string, unknown>): void
  (e: 'add-child', title: string, notes: string): void
  (e: 'delete'): void
}>()

const title = ref(props.node.title)
const notes = ref(props.node.notes)
const status = ref(props.node.status)
const drawerOpen = ref(false)
const selected = ref<StatBlockDTO | null>(null)
const childTitle = ref('')
const childNotes = ref('')

watch(() => props.node, (n) => {
  title.value = n.title
  notes.value = n.notes
  status.value = n.status
}, { deep: true })

const dirty = computed(() =>
  title.value !== props.node.title
  || notes.value !== props.node.notes
  || status.value !== props.node.status,
)

function save(): void {
  emit('patch', { title: title.value, notes: notes.value, status: status.value })
}

async function openStat(ref_: string): Promise<void> {
  const m = ref_.match(/^Ref([A-Za-z0-9_-]+)/)
  if (!m) {
    ElMessage.warning(`无法解析 ref: ${ref_}`)
    return
  }
  try {
    selected.value = await getStat(props.projectId, m[1])
    drawerOpen.value = true
  } catch {
    ElMessage.error('获取 stat 失败')
  }
}

function addChild(): void {
  const t = childTitle.value.trim()
  if (!t) {
    ElMessage.warning('请填写子节标题')
    return
  }
  emit('add-child', t, childNotes.value.trim())
  childTitle.value = ''
  childNotes.value = ''
}
</script>

<template>
  <div class="node-detail">
    <header class="head">
      <div>
        <span class="sid">{{ node.id }}</span>
        <span class="ref">{{ node.principle_ref }}</span>
      </div>
      <div class="status-pick">
        状态：
        <el-select v-model="status" size="small" style="width: 120px">
          <el-option value="pending" label="待写" />
          <el-option value="writing" label="撰写中" />
          <el-option value="done" label="完成" />
          <el-option value="editing" label="编辑" />
        </el-select>
      </div>
    </header>

    <section class="block">
      <label>标题</label>
      <el-input v-model="title" />
    </section>

    <section class="block">
      <label>项目特化说明（notes）</label>
      <el-input v-model="notes" type="textarea" :rows="4"
                placeholder="说明这一节在本项目中的特殊处理；写手 agent 会读到。" />
    </section>

    <section class="block" v-if="node.stat_hints?.length">
      <label>统计提示（来自 principle）</label>
      <ul class="hints">
        <li v-for="h in node.stat_hints" :key="h">{{ h }}</li>
      </ul>
    </section>

    <section class="block">
      <label>已绑定 StatBlock ({{ node.stat_refs.length }})</label>
      <div v-if="!node.stat_refs.length" class="muted">尚未绑定</div>
      <ul v-else class="refs">
        <li v-for="r in node.stat_refs" :key="r">
          <code>{{ r }}</code>
          <el-button size="small" link type="primary" @click="openStat(r)">查看 stat</el-button>
        </li>
      </ul>
    </section>

    <section class="block">
      <label>已绑定文献 ({{ node.literature_refs.length }})</label>
      <div v-if="!node.literature_refs.length" class="muted">尚未绑定</div>
      <ul v-else class="refs">
        <li v-for="r in node.literature_refs" :key="r">
          <code>{{ r }}</code>
        </li>
      </ul>
    </section>

    <section class="block">
      <label>新增子节</label>
      <div class="row">
        <el-input v-model="childTitle" placeholder="子节标题" size="small" style="flex:1" />
        <el-input v-model="childNotes" placeholder="备注（可选）" size="small" style="flex:2" />
        <el-button size="small" @click="addChild">添加</el-button>
      </div>
    </section>

    <footer class="foot">
      <el-button type="primary" :disabled="!dirty" @click="save">保存修改</el-button>
      <el-button type="danger" plain @click="emit('delete')">删除该节</el-button>
    </footer>

    <StatBlockDrawer v-model:open="drawerOpen" :block="selected" />
  </div>
</template>

<style scoped>
.node-detail { display: flex; flex-direction: column; gap: 16px; }
.head { display: flex; justify-content: space-between; align-items: center; }
.head .sid { font-family: ui-monospace, monospace; color: #4b5563; margin-right: 12px; }
.head .ref { color: #1d4ed8; font-family: ui-monospace, monospace; font-size: 12px; }
.block label { display: block; font-size: 12px; color: #6b7280; margin-bottom: 4px; }
.muted { color: #9ca3af; font-size: 12px; }
.hints { padding-left: 18px; color: #4b5563; }
.refs { padding-left: 0; list-style: none; }
.refs li { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.refs code { background: #f1f5f9; padding: 1px 6px; border-radius: 3px; font-size: 12px; }
.row { display: flex; gap: 8px; }
.foot { display: flex; gap: 8px; margin-top: 4px; }
</style>
