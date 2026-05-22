<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const projectName = computed(() => (route.params.id ? `Project ${String(route.params.id).slice(0, 8)}` : 'AutoCSR'))

const steps = [
  { key: 'intake', label: '上传' },
  { key: 'cleanse', label: '清洗' },
  { key: 'analyze', label: '分析' },
  { key: 'outline', label: '大纲' },
  { key: 'report', label: '撰写' },
  { key: 'export', label: '导出' },
]
</script>

<template>
  <el-container class="autocsr-shell" direction="vertical">
    <el-header class="autocsr-header">
      <div class="brand">AutoCSR · {{ projectName }}</div>
      <nav class="steps">
        <span v-for="(s, i) in steps" :key="s.key" class="step">
          <span class="num">{{ i + 1 }}</span>
          <span class="label">{{ s.label }}</span>
        </span>
      </nav>
      <div class="actions">
        <el-tag size="small" type="info">M1 skeleton</el-tag>
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
}
.steps {
  display: flex;
  gap: 16px;
  color: #6b7280;
  font-size: 13px;
}
.step {
  display: inline-flex;
  align-items: center;
  gap: 6px;
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
.autocsr-main {
  padding: 0;
  background: #f5f7fa;
  overflow: hidden;
}
</style>
