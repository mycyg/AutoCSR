<script setup lang="ts">
/**
 * Jupyter-style code cell: shows generated python, lets the user re-run
 * an edited version against the sandbox, and surfaces stdout / stderr /
 * artifact thumbnails.
 *
 * Editor uses a plain textarea — Monaco would add ~5 MB to the bundle for
 * a feature only power users touch; we can swap it later.
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '@/api/rest'

const props = defineProps<{
  projectId: string
  code: string
  initialStdout?: string
  initialStderr?: string
  initialArtifacts?: string[]
  runId?: string | null
}>()

const draft = ref(props.code)
const stdout = ref(props.initialStdout ?? '')
const stderr = ref(props.initialStderr ?? '')
const artifacts = ref<string[]>(props.initialArtifacts ?? [])
const runId = ref<string | null>(props.runId ?? null)
const running = ref(false)
const showStderr = ref(false)

const pngArtifacts = computed(() =>
  artifacts.value.filter((p) => /\.png$/i.test(p)),
)

function artifactUrl(absPath: string): string {
  const file = absPath.split(/[\\/]/).pop() ?? ''
  return runId.value
    ? `/api/projects/${props.projectId}/sandbox/runs/${runId.value}/artifacts/${file}`
    : ''
}

async function rerun(): Promise<void> {
  if (!draft.value.trim()) {
    ElMessage.warning('代码为空')
    return
  }
  running.value = true
  try {
    const r = await api.post(
      `/projects/${props.projectId}/sandbox/run`,
      { code: draft.value, timeout: 45, mem_mb: 1024 },
      { timeout: 120_000 },
    )
    stdout.value = r.data.stdout || ''
    stderr.value = r.data.stderr || ''
    artifacts.value = r.data.artifacts || []
    runId.value = r.data.run_id || null
    if (r.data.exit_code !== 0) {
      ElMessage.warning(`沙盒非零退出 (${r.data.exit_code})${r.data.error ? ': ' + r.data.error : ''}`)
    } else {
      ElMessage.success('运行完成')
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    running.value = false
  }
}
</script>

<template>
  <div class="code-run-card">
    <header class="bar">
      <span class="label">沙盒代码</span>
      <span v-if="runId" class="rid">run: {{ runId }}</span>
      <el-button size="small" type="primary" :loading="running" @click="rerun">重跑</el-button>
    </header>
    <div class="editor">
      <textarea v-model="draft" spellcheck="false" wrap="off" rows="12" />
    </div>
    <div v-if="stdout" class="stdout">
      <span class="block-label">stdout</span>
      <pre>{{ stdout }}</pre>
    </div>
    <div v-if="stderr" class="stderr">
      <span class="block-label clickable" @click="showStderr = !showStderr">
        stderr {{ showStderr ? '−' : '+' }}
      </span>
      <pre v-if="showStderr">{{ stderr }}</pre>
    </div>
    <div v-if="pngArtifacts.length" class="artifacts">
      <span class="block-label">图表 artifacts</span>
      <div class="thumbs">
        <a v-for="a in pngArtifacts" :key="a" :href="artifactUrl(a)" target="_blank">
          <img :src="artifactUrl(a)" :alt="a" />
        </a>
      </div>
    </div>
  </div>
</template>

<style scoped>
.code-run-card { border: 1px solid #e5e7eb; border-radius: 6px; background: #fff; }
.bar { display: flex; align-items: center; gap: 12px; padding: 8px 12px; border-bottom: 1px solid #f1f5f9; }
.bar .label { font-weight: 600; color: #1f2937; font-size: 13px; }
.bar .rid { font-family: ui-monospace, monospace; font-size: 11px; color: #6b7280; margin-right: auto; }
.editor textarea {
  width: 100%; box-sizing: border-box;
  font-family: ui-monospace, "JetBrains Mono", monospace; font-size: 12px;
  line-height: 1.5; padding: 10px 12px; border: none; outline: none; resize: vertical;
  background: #0f172a; color: #f8fafc;
}
.stdout, .stderr { padding: 8px 12px; border-top: 1px solid #f1f5f9; }
.stdout pre, .stderr pre {
  white-space: pre-wrap; word-break: break-word;
  font-family: ui-monospace, monospace; font-size: 12px;
  max-height: 220px; overflow: auto; margin: 6px 0 0;
  background: #f9fafb; padding: 8px 10px; border-radius: 4px;
}
.stderr pre { background: #fef2f2; color: #b91c1c; }
.block-label { font-size: 11px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.04em; }
.clickable { cursor: pointer; user-select: none; }
.artifacts { padding: 8px 12px; border-top: 1px solid #f1f5f9; }
.thumbs { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 6px; }
.thumbs img { max-height: 140px; max-width: 240px; border: 1px solid #e5e7eb; border-radius: 4px; background: #fff; }
</style>
