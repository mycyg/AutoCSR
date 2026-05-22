import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'project-list',
    component: () => import('@/views/ProjectList.vue'),
  },
  {
    path: '/p/:id',
    name: 'project-detail',
    component: () => import('@/views/ProjectDetail.vue'),
    props: true,
  },
  {
    path: '/p/:id/intake',
    name: 'project-intake',
    component: () => import('@/views/IntakeView.vue'),
    props: true,
  },
  {
    path: '/p/:id/cleanse',
    name: 'project-cleanse',
    component: () => import('@/views/CleanseView.vue'),
    props: true,
  },
  {
    path: '/p/:id/analyze',
    name: 'project-analyze',
    component: () => import('@/views/AnalyzeView.vue'),
    props: true,
  },
  {
    path: '/p/:id/outline',
    name: 'project-outline',
    component: () => import('@/views/OutlineView.vue'),
    props: true,
  },
  {
    path: '/p/:id/report',
    name: 'project-report',
    component: () => import('@/views/ReportView.vue'),
    props: true,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
