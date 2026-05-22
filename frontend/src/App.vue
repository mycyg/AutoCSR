<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => (route.params.id as string | undefined) || '')
const projectName = computed(() => (projectId.value ? `Project ${projectId.value.slice(0, 8)}` : 'AutoCSR'))

const steps = [
  { key: 'intake', label: '上传', path: 'intake', enabled: true },
  { key: 'cleanse', label: '清洗', path: 'cleanse', enabled: true },
  { key: 'analyze', label: '分析', path: 'analyze', enabled: true },
  { key: 'outline', label: '大纲', path: 'outline', enabled: true },
  { key: 'report', label: '撰写', path: 'report', enabled: false },
  { key: 'export', label: '导出', path: 'export', enabled: false },
]

const activeKey = computed(() => {
  const n = String(route.name || '')
  if (n.includes('intake')) return 'intake'
  if (n.includes('cleanse')) return 'cleanse'
  if (n.includes('analyze')) return 'analyze'
  if (n.includes('outline')) return 'outline'
  if (n === 'project-detail') return 'intake'
  return ''
})

function go(step: typeof steps[number]): void {
  if (!step.enabled || !projectId.value) return
  router.push(`/p/${projectId.value}/${step.path}`)
}
</script>

<template>
  <el-container class="autocsr-shell" direction="vertical">
    <el-header class="autocsr-header">
      <div class="brand" @click="router.push('/')">AutoCSR · {{ projectName }}</div>
      <nav class="steps">
        <span v-for="(s, i) in steps" :key="s.key"
              class="step"
              :class="{ active: activeKey === s.key, disabled: !s.enabled || !projectId }"
              @click="go(s)">
          <span class="num">{{ i + 1 }}</span>
          <span class="label">{{ s.label }}</span>
        </span>
      </nav>
      <div class="actions">
        <el-tag size="small" type="success">M3</el-tag>
      </div>
    </el-header>
    <el-main class="autocsr-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style scoped>
.autocsr-shell {
  height: 100vh;
}
.autocsr-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
  height: 56px;
}
.brand {
  font-weight: 600;
  font-size: 16px;
  color: #1f2937;
  cursor: pointer;
}
.steps {
  display: flex;
  gap: 14px;
  color: #6b7280;
  font-size: 13px;
}
.step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 12px;
  transition: background 120ms ease;
}
.step:hover:not(.disabled) {
  background: #f3f4f6;
  color: #1f2937;
}
.step.active {
  background: #eef4ff;
  color: #1d4ed8;
}
.step.disabled {
  cursor: not-allowed;
  opacity: 0.45;
}
.step .num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: #f3f4f6;
  font-size: 11px;
}
.step.active .num {
  background: #1d4ed8;
  color: #fff;
}
.autocsr-main {
  padding: 0;
  background: #f5f7fa;
  overflow: hidden;
}
</style>
