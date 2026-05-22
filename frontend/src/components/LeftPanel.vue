<script setup lang="ts">
defineProps<{ projectId: string }>()
</script>

<template>
  <div class="left-panel">
    <header class="hdr">
      <span class="title">左 Panel</span>
      <el-tag size="small" type="info">M1 占位</el-tag>
    </header>
    <div class="body">
      <p class="hint">
        M2 起：左栏会渲染 TOC 树 / 文件列表 / 数据 StatBlock。
      </p>
      <p class="meta">project id: <code>{{ projectId }}</code></p>
    </div>
  </div>
</template>

<style scoped>
.left-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.hdr {
  padding: 12px 16px;
  border-bottom: 1px solid #e4e7ed;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.title {
  font-weight: 600;
  color: #374151;
  font-size: 13px;
}
.body {
  padding: 16px;
  color: #6b7280;
  font-size: 13px;
}
.hint {
  margin: 0 0 12px;
  line-height: 1.6;
}
.meta {
  margin: 0;
  font-size: 12px;
  color: #9ca3af;
}
</style>
