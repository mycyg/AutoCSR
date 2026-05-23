<script setup lang="ts">
import { onMounted, watch } from 'vue'
import LeftPanel from '@/components/LeftPanel.vue'
import CenterEditor from '@/components/CenterEditor.vue'
import RightPanel from '@/components/RightPanel.vue'
import { useProjectStore } from '@/stores/project'

const props = defineProps<{ id: string }>()
const store = useProjectStore()

onMounted(() => store.load(props.id))
watch(() => props.id, (id) => store.load(id))
</script>

<template>
  <el-container class="detail">
    <el-aside class="left" width="280px">
      <LeftPanel :project-id="props.id" />
    </el-aside>
    <el-main class="center">
      <CenterEditor :project-id="props.id" />
    </el-main>
    <el-aside class="right" width="360px">
      <RightPanel :project-id="props.id" />
    </el-aside>
  </el-container>
</template>

<style scoped>
.detail {
  height: 100%;
}
.left {
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  overflow: auto;
}
.center {
  padding: 0;
  background: var(--color-surface-2);
  overflow: auto;
}
.right {
  background: var(--color-surface);
  border-left: 1px solid var(--color-border);
  overflow: auto;
}
@media (max-width: 1279px) {
  .left { width: 220px !important; }
  .right { width: 300px !important; }
}
@media (max-width: 1023px) {
  .detail { flex-direction: column; }
  .left, .right { width: auto !important; max-height: 200px; border: none; border-bottom: 1px solid var(--color-border); }
}
</style>
