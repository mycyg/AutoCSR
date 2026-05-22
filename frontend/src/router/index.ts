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
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
