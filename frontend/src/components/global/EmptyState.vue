<script setup lang="ts">
/**
 * Generic empty-state UI for views.
 *
 * Usage:
 *   <EmptyState v-if="!items.length"
 *               icon="..."
 *               :title="$t('analyze.empty_title')"
 *               :description="$t('analyze.empty_desc')"
 *               :cta-text="$t('analyze.auto_run')"
 *               @cta="onAuto" />
 *
 * Keep this purely presentational — no store calls.
 */
defineProps<{
  icon?: string
  title?: string
  description?: string
  ctaText?: string
}>()

defineEmits<{ (e: 'cta'): void }>()
</script>

<template>
  <div class="empty-state" role="status" aria-live="polite">
    <div v-if="icon" class="icon" aria-hidden="true">{{ icon }}</div>
    <h3 v-if="title" class="title">{{ title }}</h3>
    <p v-if="description" class="desc">{{ description }}</p>
    <el-button v-if="ctaText" type="primary" plain class="cta"
                @click="$emit('cta')">{{ ctaText }}</el-button>
    <slot />
  </div>
</template>

<style scoped>
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 24px;
  color: var(--color-text-mute);
  text-align: center;
  gap: 8px;
}
.empty-state .icon {
  font-size: 48px;
  opacity: 0.65;
  margin-bottom: 8px;
}
.empty-state .title {
  margin: 0;
  font-size: var(--font-size-xl);
  font-weight: 600;
  color: var(--color-text-strong);
}
.empty-state .desc {
  margin: 0;
  max-width: 420px;
  font-size: var(--font-size-md);
  line-height: 1.55;
}
.empty-state .cta {
  margin-top: 12px;
}
</style>
