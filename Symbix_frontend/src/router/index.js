import { createRouter, createWebHistory } from 'vue-router'
import HomePage from '../pages/Home.vue'
import SettingPage from '../pages/Setting.vue'
import testPage from '../pages/test.vue'
import ChatWindowPage from '../pages/chat_window.vue'
import SkinWindowPage from '../pages/SkinWindow.vue'

const routes = [
  {
    path: '/',
    name: 'Home',
    component: HomePage,
  },
  {
    path: '/setting',
    name: 'Setting',
    component: SettingPage,
  },
  {
    path: '/test',
    name: 'Test',
    component: testPage,
  },
  {
    path: '/chat_window',
    name: 'ChatWindow',
    component: ChatWindowPage,
  },
  {
    path: '/skin',
    name: 'SkinWindow',
    component: SkinWindowPage,
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
