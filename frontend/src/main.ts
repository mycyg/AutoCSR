import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// Element Plus dark-mode CSS variables — activated when <html class="dark">.
import 'element-plus/theme-chalk/dark/css-vars.css'
import 'md-editor-v3/lib/style.css'

// Design tokens + a11y must load BEFORE per-component styles so they
// can be overridden by component scoped styles where needed.
import '@/styles/tokens.css'
import '@/styles/element-overrides.css'
import '@/styles/a11y.css'

import App from './App.vue'
import router from './router'
import { i18n } from './i18n'

// Touch the theme composable early so the initial theme is applied
// before the first frame paints (avoids a flash of light-on-dark).
import { useTheme } from '@/composables/useTheme'
useTheme()

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(i18n)
app.use(ElementPlus)
app.mount('#app')
