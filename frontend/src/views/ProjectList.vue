<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useProjectStore } from '@/stores/project'
import type { ProjectDTO } from '@/api/rest'

const router = useRouter()
const store = useProjectStore()
const { t } = useI18n()

const dialogVisible = ref(false)
const submitting = ref(false)
const form = ref<{ name: string; principle_id: string; template_id: string }>({
  name: '', principle_id: '', template_id: '',
})

const searchQ = ref('')
const tagQ = ref<string | undefined>(undefined)
const showArchived = ref(false)
const sortBy = ref<'last_opened' | 'created' | 'name'>('last_opened')

onMounted(async () => {
  await Promise.all([store.refresh(), store.loadTemplates()])
})

let searchTimer: number | null = null
watch([searchQ, tagQ, showArchived, sortBy], () => {
  if (searchTimer !== null) window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(() => {
    void store.refresh({
      search: searchQ.value || undefined,
      tag: tagQ.value || undefined,
      archived: showArchived.value ? undefined : false,
      sort: sortBy.value,
    })
  }, 250)
})

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
    try {
      await ElMessageBox.confirm(
        t('projects.archive_confirm', { name: row.name }),
        t('common.help'), { type: 'warning' },
      )
    } catch { return }
    await store.update(row.id, { archived: true })
    ElMessage.success(t('common.ok'))
  } else if (action === 'unarchive') {
    await store.update(row.id, { archived: false })
    ElMessage.success(t('common.ok'))
  } else if (action === 'duplicate') {
    try {
      const newName = await ElMessageBox.prompt(
        t('projects.field_name'), t('projects.duplicate'),
        { inputValue: row.name + ' (copy)' },
      )
      await store.create({
        name: String(newName.value).trim(),
        principle_id: row.principle_id,
        language: row.language,
        notes: row.notes,
      })
      ElMessage.success(t('common.ok'))
    } catch { /* cancelled */ }
  } else if (action === 'delete') {
    if (!row.archived) {
      ElMessage.warning(t('projects.must_archive_first'))
      return
    }
    try {
      await ElMessageBox.confirm(
        t('projects.delete_confirm', { name: row.name }),
        t('common.delete'), { type: 'error' },
      )
    } catch { return }
    await store.remove(row.id, false)
    ElMessage.success(t('common.ok'))
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
        <el-empty v-if="!store.loading && !store.projects.length"
                  :description="$t('projects.empty_desc')" />

        <el-table v-else :data="store.projects" class="grid" stripe>
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
                <el-button link size="small">⋮</el-button>
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
.bar h2 { font-size: 18px; font-weight: 600; color: #1f2937; margin: 0; }
.bar-right { display: flex; gap: 8px; }
.filters {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 16px;
}
.filters .search { width: 280px; }
.filters .tag-filter { width: 180px; }
.filters .sort { width: 160px; }
.layout { display: flex; gap: 18px; }
.recent {
  width: 240px;
  background: #fff;
  border-radius: 8px;
  padding: 14px 18px;
  flex: 0 0 240px;
}
.recent h3 { margin: 0 0 8px 0; font-size: 13px; color: #1f2937; font-weight: 600; }
.recent ul { list-style: none; padding: 0; margin: 0; }
.recent li {
  display: flex; flex-direction: column;
  padding: 8px 0; border-bottom: 1px solid #f0f1f4;
}
.recent li:last-child { border-bottom: none; }
.recent .muted { font-size: 11px; color: #9ca3af; margin-top: 2px; }
.main { flex: 1 1 auto; }
.grid { border-radius: 6px; background: #fff; }
.link { color: #2563eb; text-decoration: none; }
.link:hover { text-decoration: underline; }
.muted { color: #9ca3af; }
.tag-inline { margin-left: 4px; }
</style>
