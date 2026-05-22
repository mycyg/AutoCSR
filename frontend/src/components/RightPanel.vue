<script setup lang="ts">
defineProps<{ projectId: string }>()
</script>

<template>
  <div class="right-panel">
    <header class="hdr">
      <span class="title">右 Panel · Chat</span>
      <el-tag size="small" type="info">M1 占位</el-tag>
    </header>
    <div class="body">
      <p class="hint">
        M4 起：右栏会承载对话编辑器 + Agent 状态浮窗。
        点击某节后在这里说 "把这段改正式些"，apply_patch 会更新中栏 markdown。
      </p>
      <p class="meta">project id: <code>{{ projectId }}</code></p>
    </div>
  </div>
</template>

<style scoped>
.right-panel {
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
