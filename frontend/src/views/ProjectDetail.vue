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
  background: #fff;
  border-right: 1px solid #e4e7ed;
  overflow: auto;
}
.center {
  padding: 0;
  background: #fafbfc;
  overflow: auto;
}
.right {
  background: #fff;
  border-left: 1px solid #e4e7ed;
  overflow: auto;
}
</style>
