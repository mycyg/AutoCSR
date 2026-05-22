<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'

const router = useRouter()
const store = useProjectStore()

const dialogVisible = ref(false)
const form = ref({ name: '', principle_id: '' })
const submitting = ref(false)

onMounted(() => store.refresh())

function openCreate(): void {
  form.value = { name: '', principle_id: '' }
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入项目名称')
    return
  }
  submitting.value = true
  try {
    const p = await store.create({
      name: form.value.name.trim(),
      principle_id: form.value.principle_id.trim() || null,
    })
    dialogVisible.value = false
    ElMessage.success(`项目 ${p.name} 已创建`)
    router.push(`/p/${p.id}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    submitting.value = false
  }
}

function fmt(ts: string): string {
  try {
    return new Date(ts).toLocaleString('zh-CN')
  } catch {
    return ts
  }
}
</script>

<template>
  <div class="project-list">
    <header class="bar">
      <h2>项目列表</h2>
      <div class="bar-right">
        <el-button :loading="store.loading" @click="store.refresh">刷新</el-button>
        <el-button type="primary" @click="openCreate">新建项目</el-button>
      </div>
    </header>

    <el-empty v-if="!store.loading && !store.projects.length" description="还没有项目，点击右上角新建一个" />

    <el-table v-else :data="store.projects" class="grid" stripe>
      <el-table-column prop="name" label="项目名称" min-width="240">
        <template #default="{ row }">
          <router-link :to="`/p/${row.id}`" class="link">{{ row.name }}</router-link>
        </template>
      </el-table-column>
      <el-table-column prop="principle_id" label="指导原则" width="160">
        <template #default="{ row }">
          <span v-if="row.principle_id">{{ row.principle_id }}</span>
          <span v-else class="muted">未选择</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="120">
        <template #default="{ row }">
          <el-tag size="small" :type="row.status === 'draft' ? 'info' : 'success'">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" width="200">
        <template #default="{ row }">{{ fmt(row.created_at) }}</template>
      </el-table-column>
      <el-table-column prop="id" label="ID" width="160">
        <template #default="{ row }"><code>{{ row.id }}</code></template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新建项目" width="480">
      <el-form label-width="100" label-position="right" @submit.prevent>
        <el-form-item label="项目名称" required>
          <el-input v-model="form.name" placeholder="例如：BMS-A001 III期临床" maxlength="200" />
        </el-form-item>
        <el-form-item label="指导原则">
          <el-input v-model="form.principle_id" placeholder="(可选) 例如 ich_e3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.project-list {
  padding: 24px 32px;
  max-width: 1280px;
  margin: 0 auto;
}
.bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.bar h2 {
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}
.bar-right {
  display: flex;
  gap: 8px;
}
.grid {
  border-radius: 6px;
  background: #fff;
}
.link {
  color: #2563eb;
  text-decoration: none;
}
.link:hover {
  text-decoration: underline;
}
.muted {
  color: #9ca3af;
}
</style>
