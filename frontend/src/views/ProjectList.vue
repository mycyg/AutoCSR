<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useProjectStore } from '@/stores/project'
import type { ProjectDTO } from '@/api/rest'
import { confirmAction } from '@/composables/useConfirm'
import { handleApiError } from '@/utils/errors'

const router = useRouter()
const store = useProjectStore()
const { t } = useI18n()

const dialogVisible = ref(false)
const submitting = ref(false)
const form = ref<{ name: string; principle_id: string; template_id: string }>({
  name: '', principle_id: '', template_id: '',
})

// M20 — sample-project dropdown (lazy-loaded on first open)
const sampleDomains = ref<Array<{ domain: string; template_id: string; name: string; blurb: string }>>([])
const sampleLoading = ref(false)

async function loadSampleDomains(): Promise<void> {
  if (sampleDomains.value.length || sampleLoading.value) return
  sampleLoading.value = true
  try {
    const res = await fetch('/api/sample_projects')
    if (res.ok) sampleDomains.value = await res.json()
  } catch (e) {
    handleApiError(e)
  } finally {
    sampleLoading.value = false
  }
}

async function createFromSample(domain: string): Promise<void> {
  submitting.value = true
  try {
    const res = await fetch(`/api/projects/from_sample/${domain}`,
                              { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({}) })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const proj = await res.json()
    await store.refresh()
    ElMessage.success(`${proj.name} (${proj.parquet_count} files staged)`)
    router.push(`/p/${proj.id}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    submitting.value = false
  }
}

const searchQ = ref('')
const tagQ = ref<string | undefined>(undefined)
const showArchived = ref(false)
const sortBy = ref<'last_opened' | 'created' | 'name'>('last_opened')

onMounted(async () => {
  await Promise.all([store.refresh(), store.loadTemplates()])
  // Eagerly hydrate sample domains so the hero grid lights up on first paint.
  void loadSampleDomains()
})

// M22 — visual helpers for the hero domain grid.
const DOMAIN_ICONS: Record<string, string> = {
  oncology: '🧬',
  rare_disease: '🧪',
  vaccine: '💉',
  pediatric: '👶',
  cardiovascular: '❤️',
}
function domainIcon(domain: string): string {
  return DOMAIN_ICONS[domain] || '📋'
}

let searchTimer: number | null = null
watch([searchQ, tagQ, showArchived, sortBy], () => {
  if (searchTimer !== null) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    void refreshWithFilters()
  }, 250)
})

function refreshWithFilters(): Promise<void> {
  return store.refresh({
    search: searchQ.value || undefined,
    tag: tagQ.value || undefined,
    archived: showArchived.value ? undefined : false,
    sort: sortBy.value,
  })
}

function openCreate(templateId = ''): void {
  form.value = { name: '', principle_id: '', template_id: templateId }
  dialogVisible.value = true
}

async function submit(): Promise<void> {
  if (!form.value.name.trim()) {
    ElMessage.warning(t('projects.field_name'))
    return
  }
  submitting.value = true
  try {
    let p: ProjectDTO
    if (form.value.template_id) {
      p = await store.createFromTemplate(form.value.template_id, form.value.name.trim())
    } else {
      p = await store.create({
        name: form.value.name.trim(),
        principle_id: form.value.principle_id.trim() || null,
      })
    }
    dialogVisible.value = false
    ElMessage.success(p.name)
    router.push(`/p/${p.id}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    submitting.value = false
  }
}

async function onContext(row: ProjectDTO, action: string): Promise<void> {
  if (action === 'archive') {
    if (!await confirmAction('projects.archive_confirm',
                              { type: 'warning', resource_name: row.name })) return
    try { await store.update(row.id, { archived: true }); await refreshWithFilters(); ElMessage.success(t('common.ok')) }
    catch (e) { handleApiError(e) }
  } else if (action === 'unarchive') {
    try { await store.update(row.id, { archived: false }); await refreshWithFilters(); ElMessage.success(t('common.ok')) }
    catch (e) { handleApiError(e) }
  } else if (action === 'duplicate') {
    try {
      await store.create({
        name: row.name + ' (copy)',
        principle_id: row.principle_id,
        language: row.language,
        notes: row.notes,
      })
      ElMessage.success(t('common.ok'))
    } catch (e) { handleApiError(e) }
  } else if (action === 'delete') {
    if (!row.archived) {
      ElMessage.warning(t('projects.must_archive_first'))
      return
    }
    if (!await confirmAction('projects.delete_confirm',
                              { type: 'error', danger: true,
                                resource_name: row.name,
                                confirm_text: 'common.delete' })) return
    try { await store.remove(row.id, false); ElMessage.success(t('common.ok')) }
    catch (e) { handleApiError(e) }
  }
}

function fmt(ts?: string | null): string {
  if (!ts) return '—'
  try { return new Date(ts).toLocaleString() } catch { return String(ts) }
}

const tagOptions = computed(() => store.allTags.map((t) => ({ value: t, label: t })))
</script>

<template>
  <div class="project-list">
    <header class="bar">
      <h2>{{ $t('projects.title') }}</h2>
      <div class="bar-right">
        <el-button :loading="store.loading" @click="store.refresh()">{{ $t('common.refresh') }}</el-button>
        <el-dropdown trigger="click" @command="(v: any) => createFromSample(String(v))"
                      @visible-change="(v: boolean) => v && loadSampleDomains()">
          <el-button :loading="submitting || sampleLoading">
            🧪 Try with Sample Data <el-icon class="el-icon--right">▾</el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item v-if="sampleLoading" disabled>Loading…</el-dropdown-item>
              <el-dropdown-item v-for="d in sampleDomains" :key="d.domain" :command="d.domain">
                <strong>{{ d.name }}</strong>
                <div style="font-size: 11px; opacity: 0.7; max-width: 280px; white-space: normal;">
                  {{ d.blurb }}
                </div>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown trigger="click" @command="(v: any) => openCreate(typeof v === 'string' ? v : '')">
          <el-button type="primary">
            {{ $t('common.new') }} <el-icon class="el-icon--right">▾</el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item :command="''">{{ $t('projects.new_blank') }}</el-dropdown-item>
              <el-dropdown-item divided disabled>{{ $t('projects.new_from_template') }}</el-dropdown-item>
              <el-dropdown-item v-for="tpl in store.templates" :key="tpl.id" :command="tpl.id">
                {{ tpl.name }}
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </header>

    <div class="filters">
      <el-input v-model="searchQ" :placeholder="$t('projects.search_placeholder')" clearable
                class="search" prefix-icon="🔍" />
      <el-select v-model="tagQ" :placeholder="$t('projects.tag_filter')" clearable
                 class="tag-filter">
        <el-option v-for="o in tagOptions" :key="o.value" :value="o.value" :label="o.label" />
      </el-select>
      <el-select v-model="sortBy" class="sort">
        <el-option value="last_opened" :label="$t('common.last_opened')" />
        <el-option value="created" :label="$t('common.created_at')" />
        <el-option value="name" :label="$t('common.name')" />
      </el-select>
      <el-checkbox v-model="showArchived">{{ $t('projects.show_archived') }}</el-checkbox>
    </div>

    <div class="layout">
      <aside class="recent" v-if="store.recent.length">
        <h3>★ {{ $t('projects.recent') }}</h3>
        <ul>
          <li v-for="r in store.recent" :key="r.id">
            <router-link :to="`/p/${r.id}`" class="link">{{ r.name }}</router-link>
            <span class="muted">{{ fmt(r.last_opened_at) }}</span>
          </li>
        </ul>
      </aside>

      <section class="main">
        <div v-if="!store.loading && !store.projects.length" class="hero-empty">
          <div class="hero">
            <div class="hero-icon" aria-hidden="true">📑</div>
            <h1>{{ $t('app.title') }}</h1>
            <p class="hero-pitch">{{ $t('projects.hero_pitch') }}</p>
            <!-- TODO: hero video — replace with real demo .mp4 / .gif when ready -->
            <div class="hero-video" role="img"
                  :aria-label="$t('projects.hero_video_alt')">
              <span aria-hidden="true">▶</span>
              <span class="muted">30s demo video — coming soon</span>
            </div>
            <el-button type="primary" size="large" @click="openCreate('')">
              {{ $t('common.new') }}
            </el-button>
          </div>
          <!-- M22 — 5 domain demo project cards, more prominent than the
                dropdown.  Clicking a card kicks off `create-from-sample`. -->
          <section v-if="sampleDomains.length" class="domains" aria-labelledby="hero-domains-title">
            <h3 id="hero-domains-title">{{ $t('projects.try_sample_title') }}</h3>
            <p class="domains-sub">{{ $t('projects.try_sample_sub') }}</p>
            <div class="dom-grid">
              <article v-for="d in sampleDomains" :key="d.domain"
                        class="dom-card" tabindex="0" role="button"
                        :aria-label="`${d.name}: ${d.blurb}`"
                        @click="createFromSample(d.domain)"
                        @keyup.enter="createFromSample(d.domain)">
                <div class="dom-icon" aria-hidden="true">{{ domainIcon(d.domain) }}</div>
                <div class="dom-name">{{ d.name }}</div>
                <div class="dom-blurb">{{ d.blurb }}</div>
                <div class="dom-cta">{{ $t('projects.start_demo') }} →</div>
              </article>
            </div>
          </section>

          <div v-if="store.templates.length" class="templates">
            <h3>{{ $t('projects.templates_title') }}</h3>
            <div class="tpl-grid">
              <article v-for="tpl in store.templates.slice(0, 4)" :key="tpl.id"
                        class="tpl-card" tabindex="0" role="button"
                        :aria-label="tpl.name"
                        @click="openCreate(tpl.id)"
                        @keyup.enter="openCreate(tpl.id)">
                <div class="tpl-icon" aria-hidden="true">{{
                  tpl.id.includes('safety') ? '🛡' :
                  tpl.id.includes('onco') ? '🧬' :
                  tpl.id.includes('device') ? '⚙' : '📋'
                }}</div>
                <div class="tpl-name">{{ tpl.name }}</div>
                <div class="tpl-desc">{{ tpl.description || $t('projects.tpl_default_desc') }}</div>
                <div class="tpl-cta">{{ $t('projects.use_template') }} →</div>
              </article>
            </div>
          </div>
        </div>

        <el-table v-else :data="store.projects" class="grid" stripe role="table">
          <el-table-column :label="$t('common.name')" min-width="240">
            <template #default="{ row }">
              <router-link :to="`/p/${row.id}`" class="link">{{ row.name }}</router-link>
              <el-tag v-if="row.archived" size="small" type="info" class="tag-inline">archived</el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.tags')" width="220">
            <template #default="{ row }">
              <el-tag v-for="t in (row.tags || [])" :key="t" size="small" class="tag-inline">{{ t }}</el-tag>
              <span v-if="!(row.tags || []).length" class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('projects.principle')" width="140">
            <template #default="{ row }">
              <span v-if="row.principle_id">{{ row.principle_id }}</span>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.status')" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.status === 'draft' ? 'info' : 'success'">
                {{ row.status }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="$t('common.last_opened')" width="180">
            <template #default="{ row }">{{ fmt(row.last_opened_at) }}</template>
          </el-table-column>
          <el-table-column :label="$t('common.more')" width="100">
            <template #default="{ row }">
              <el-dropdown trigger="click" @command="(v: string) => onContext(row, v)">
                <el-button link size="small" :aria-label="$t('common.more')">⋮</el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="duplicate">{{ $t('projects.duplicate') }}</el-dropdown-item>
                    <el-dropdown-item v-if="!row.archived" command="archive">
                      {{ $t('projects.archive') }}
                    </el-dropdown-item>
                    <el-dropdown-item v-else command="unarchive">
                      {{ $t('projects.unarchive') }}
                    </el-dropdown-item>
                    <el-dropdown-item command="delete" divided>
                      {{ $t('projects.delete') }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-table-column>
        </el-table>
      </section>
    </div>

    <el-dialog v-model="dialogVisible" :title="$t('common.new')" width="480">
      <el-form label-width="100" label-position="right" @submit.prevent>
        <el-form-item :label="$t('projects.field_name')" required>
          <el-input v-model="form.name" :placeholder="$t('projects.field_name_placeholder')" maxlength="200" />
        </el-form-item>
        <el-form-item v-if="!form.template_id" :label="$t('projects.principle')">
          <el-input v-model="form.principle_id"
                    :placeholder="$t('projects.field_principle_placeholder')" />
        </el-form-item>
        <el-form-item v-else :label="$t('projects.field_template')">
          <el-tag>{{ form.template_id }}</el-tag>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ $t('common.cancel') }}</el-button>
        <el-button type="primary" :loading="submitting" @click="submit">{{ $t('common.ok') }}</el-button>
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
  margin-bottom: 12px;
}
.bar h2 { font-size: var(--font-size-2xl); font-weight: 600; color: var(--color-text-strong); margin: 0; }
.bar-right { display: flex; gap: 8px; }
.filters {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.filters .search { width: 280px; }
.filters .tag-filter { width: 180px; }
.filters .sort { width: 160px; }
.layout { display: flex; gap: 18px; }
.recent {
  width: 240px;
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  padding: 14px 18px;
  flex: 0 0 240px;
}
.recent h3 { margin: 0 0 8px 0; font-size: var(--font-size-md); color: var(--color-text-strong); font-weight: 600; }
.recent ul { list-style: none; padding: 0; margin: 0; }
.recent li {
  display: flex; flex-direction: column;
  padding: 8px 0; border-bottom: 1px solid var(--color-border);
}
.recent li:last-child { border-bottom: none; }
.recent .muted { font-size: var(--font-size-xs); color: var(--color-text-mute); margin-top: 2px; }
.main { flex: 1 1 auto; }
.grid { border-radius: var(--radius-md); background: var(--color-surface); }
.link { color: var(--color-primary); text-decoration: none; }
.link:hover { text-decoration: underline; }
.muted { color: var(--color-text-mute); }
.tag-inline { margin-left: 4px; }

/* Hero empty state */
.hero-empty {
  display: flex;
  flex-direction: column;
  gap: 32px;
  padding: 32px 0;
}
.hero {
  text-align: center;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 56px 32px;
}
.hero-icon { font-size: 64px; margin-bottom: 16px; }
.hero h1 { margin: 0; font-size: 28px; color: var(--color-text-strong); }
.hero-pitch {
  color: var(--color-text-mute);
  max-width: 480px;
  margin: 12px auto 24px;
  line-height: 1.6;
}
.hero-video {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  padding: 24px 32px;
  background: var(--color-surface-2);
  border: 1px dashed var(--color-border-strong);
  border-radius: var(--radius-lg);
  margin: 0 auto 24px;
  color: var(--color-text-mute);
}
.hero-video span:first-child { font-size: 28px; }
.templates h3 {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-text-strong);
  margin: 0 0 12px;
}
.tpl-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 16px;
}
.tpl-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 20px;
  cursor: pointer;
  transition: border-color 120ms, transform 120ms;
}
.tpl-card:hover, .tpl-card:focus-visible {
  border-color: var(--color-primary);
  transform: translateY(-2px);
}
.tpl-icon { font-size: 28px; margin-bottom: 8px; }
.tpl-name {
  font-weight: 600;
  color: var(--color-text-strong);
  font-size: var(--font-size-lg);
}
.tpl-desc {
  color: var(--color-text-mute);
  font-size: var(--font-size-sm);
  margin: 6px 0 12px;
  min-height: 36px;
}
.tpl-cta {
  color: var(--color-primary);
  font-size: var(--font-size-sm);
  font-weight: 600;
}

/* M22 — 5 domain demo project grid (sits between hero + templates). */
.domains {
  padding: 0;
  margin-top: -16px;
}
.domains h3 {
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--color-text-strong);
  margin: 0 0 6px;
}
.domains-sub {
  margin: 0 0 14px;
  color: var(--color-text-mute);
  font-size: var(--font-size-sm);
}
.dom-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
}
.dom-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: 18px 16px;
  cursor: pointer;
  text-align: center;
  transition: border-color 120ms, transform 120ms, box-shadow 120ms;
}
.dom-card:hover,
.dom-card:focus-visible {
  border-color: var(--color-primary);
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  outline: none;
}
.dom-icon { font-size: 36px; line-height: 1; margin-bottom: 8px; }
.dom-name {
  font-weight: 600;
  color: var(--color-text-strong);
  font-size: var(--font-size-lg);
  margin-bottom: 4px;
}
.dom-blurb {
  color: var(--color-text-mute);
  font-size: var(--font-size-sm);
  min-height: 32px;
  line-height: 1.4;
}
.dom-cta {
  color: var(--color-primary);
  font-size: var(--font-size-sm);
  font-weight: 600;
  margin-top: 8px;
}

/* Responsive: < 1024px collapses table to card stack */
@media (max-width: 1023px) {
  .project-list { padding: 16px; }
  .layout { flex-direction: column; }
  .recent { width: auto; flex: none; }
  :deep(.el-table) {
    /* Light card-stack tweak: table still works but rows wrap nicely. */
    font-size: var(--font-size-sm);
  }
  .filters .search,
  .filters .tag-filter,
  .filters .sort { width: 100%; }
}
@media (max-width: 767px) {
  .project-list { padding: 10px 8px; max-width: 100vw; }
  .bar { flex-direction: column; align-items: stretch; gap: 8px; }
  .bar-right { flex-wrap: wrap; }
  .hero { padding: 32px 16px; }
  .hero h1 { font-size: 22px; }
  .tpl-grid, .dom-grid { grid-template-columns: 1fr 1fr; }
}
</style>
