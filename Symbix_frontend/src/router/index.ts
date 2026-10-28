import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import HomePage from '../pages/Home.vue'
import SettingPage from '../pages/Setting.vue'
import ChatWindowPage from '../pages/chat_window.vue'
import SkinWindowPage from '../pages/SkinWindow.vue'
import ModelSettingPage from '../pages/model_setting.vue'
import DanmakuWindowPage from '../pages/DanmakuWindow.vue'
import JournalWindowPage from '../pages/JournalWindow.vue'
import UpdateWindowPage from '../pages/UpdateWindow.vue'

const routes: RouteRecordRaw[] = [
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
    path: '/chat_window',
    name: 'ChatWindow',
    component: ChatWindowPage,
  },
  {
    path: '/skin',
    name: 'SkinWindow',
    component: SkinWindowPage,
  },
  {
    path: '/model_setting',
    name: 'ModelSetting',
    component: ModelSettingPage,
  },
  {
    path: '/danmaku',
    name: 'DanmakuWindow',
    component: DanmakuWindowPage,
  },
  {
    path: '/journal',
    name: 'JournalWindow',
    component: JournalWindowPage,
  },
  {
    path: '/update',
    name: 'UpdateWindow',
    component: UpdateWindowPage,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
