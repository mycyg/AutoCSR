<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { MdPreview } from 'md-editor-v3'
import 'md-editor-v3/lib/preview.css'
import type { StatBlockDTO } from '@/api/rest'
import SubgroupForest from '@/components/analyze/SubgroupForest.vue'
import ConsortFlow from '@/components/analyze/ConsortFlow.vue'
import { sanitizeMarkdownHtml } from '@/utils/sanitize'

const props = defineProps<{ open: boolean; block: StatBlockDTO | null }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

const visible = computed({
  get: () => props.open,
  set: (v: boolean) => emit('update:open', v),
})

const PAGE_SIZE = 20
const page = ref(1)

watch(() => props.block?.ref_code, () => { page.value = 1 })

const paged = computed(() => {
  const md = props.block?.markdown_table || ''
  if (!md.trim()) return { text: '_no table_', total: 0, pages: 1 }
  const lines = md.split(/\r?\n/)
  // Detect a GFM-style table: header line + separator (---) + body rows
  const headerIdx = lines.findIndex((ln) => /^\s*\|.*\|\s*$/.test(ln))
  const sepIdx = headerIdx >= 0 && /^\s*\|[\s:-|]+\|\s*$/.test(lines[headerIdx + 1] || '')
    ? headerIdx + 1 : -1
  if (sepIdx < 0) return { text: md, total: 0, pages: 1 }
  const header = lines.slice(headerIdx, sepIdx + 1)
  const body = lines.slice(sepIdx + 1).filter((ln) => /^\s*\|/.test(ln))
  const tail = lines.slice(sepIdx + 1 + body.length)
  const pages = Math.max(1, Math.ceil(body.length / PAGE_SIZE))
  if (page.value > pages) page.value = pages
  const start = (page.value - 1) * PAGE_SIZE
  const slice = body.slice(start, start + PAGE_SIZE)
  return {
    text: [...lines.slice(0, headerIdx), ...header, ...slice, ...tail].join('\n'),
    total: body.length,
    pages,
  }
})

function refCopy(): void {
  if (props.block?.ref_code) {
    void navigator.clipboard.writeText(props.block.ref_code)
  }
}

const subgroupRows = computed(() => {
  const b = props.block
  if (!b || b.analysis_type !== 'subgroup') return null
  const rows = (b.result_json as any)?.rows
  return Array.isArray(rows) ? rows : null
})
const consortPayload = computed(() => {
  const b = props.block
  if (!b || b.analysis_type !== 'consort') return null
  const rj = (b.result_json as any) || {}
  return rj.stages ? { stages: rj.stages, arms: rj.arms || [], mermaid: rj.mermaid || '' } : null
})
</script>

<template>
  <el-drawer v-model="visible" direction="rtl" size="64%" :destroy-on-close="true">
    <template #header>
      <div class="hdr" v-if="block">
        <h3>{{ block.title }}</h3>
        <div class="meta">
          <el-tag size="small">{{ block.analysis_type }}</el-tag>
          <span class="ref" @click="refCopy" title="点击复制引用">{{ block.ref_code }}</span>
        </div>
      </div>
    </template>
    <div v-if="block" class="body">
      <section v-if="subgroupRows" class="card">
        <h4>森林图（亚组）</h4>
        <SubgroupForest :rows="subgroupRows" />
      </section>
      <section v-if="consortPayload" class="card">
        <h4>CONSORT 受试者流程</h4>
        <ConsortFlow :stages="consortPayload.stages" :arms="consortPayload.arms"
                     :mermaid="consortPayload.mermaid" />
      </section>
      <section class="card">
        <h4>渲染后表格
          <span v-if="paged.total > 20" class="muted">
            · {{ paged.total }} rows · page {{ page }}/{{ paged.pages }}
          </span>
        </h4>
        <MdPreview :modelValue="paged.text" :theme="'light'"
                   :sanitize="sanitizeMarkdownHtml" />
        <el-pagination v-if="paged.pages > 1" :total="paged.total"
                       :page-size="20" :current-page="page"
                       layout="prev, pager, next" small
                       @current-change="(v: number) => page = v" />
      </section>
      <section class="card">
        <h4>原始结果（result_json）</h4>
        <el-collapse>
          <el-collapse-item title="展开 JSON 树">
            <pre class="json">{{ JSON.stringify(block.result_json, null, 2) }}</pre>
          </el-collapse-item>
        </el-collapse>
      </section>
      <section class="card">
        <h4>参数 / 来源</h4>
        <ul class="params">
          <li v-for="(v, k) in block.params" :key="k as string">
            <code>{{ k }}</code>: {{ typeof v === 'object' ? JSON.stringify(v) : String(v) }}
          </li>
        </ul>
        <div class="srcs">
          来源文件：
          <span v-for="s in block.source_files" :key="s" class="src">{{ s }}</span>
        </div>
        <div v-if="block.notes?.length" class="notes">
          备注：{{ block.notes.join(' · ') }}
        </div>
      </section>
    </div>
  </el-drawer>
</template>

<style scoped>
.hdr h3 { margin: 0; font-size: 16px; }
.hdr .meta { margin-top: 6px; display: flex; gap: 10px; align-items: center; }
.hdr .ref {
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px;
  color: #1d4ed8; cursor: pointer;
}
.body { padding: 6px 4px; }
.card { background: #fff; border: 1px solid #e5e7eb; border-radius: 6px; padding: 14px 18px; margin-bottom: 16px; }
.card h4 { margin: 0 0 10px 0; font-size: 14px; color: #374151; }
.json { background: #0f172a; color: #f8fafc; padding: 12px; border-radius: 4px; font-size: 12px; max-height: 320px; overflow: auto; }
.params { padding-left: 18px; margin: 0; color: #4b5563; }
.params li { margin: 3px 0; font-size: 13px; }
.params code { background: #f1f5f9; padding: 1px 6px; border-radius: 3px; }
.srcs { margin-top: 8px; color: #4b5563; font-size: 12px; }
.srcs .src { display: inline-block; margin-right: 8px; }
.notes { margin-top: 8px; color: #6b7280; font-size: 12px; }
.muted { color: #9ca3af; font-weight: normal; font-size: 12px; }
</style>
