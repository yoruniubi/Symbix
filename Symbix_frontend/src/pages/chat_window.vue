<template>
  <div class="layout">
    <TitleBar />

    <!-- VSCode-style Activity Bar -->
    <div class="activity-bar">
      <div class="activity-bar-top">
        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <div class="activity-btn" :class="{ active: activePanel === 'skill' }" @click="togglePanel('skill')">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <polygon points="12 2 22 8.5 22 15.5 12 22 2 15.5 2 8.5 12 2"></polygon>
                <line x1="12" y1="22" x2="12" y2="15.5"></line>
                <polyline points="22 8.5 12 15.5 2 8.5"></polyline>
              </svg>
            </div>
          </template>
          Skill
        </n-tooltip>
        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <div class="activity-btn" :class="{ active: activePanel === 'mcp' }" @click="togglePanel('mcp')">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect>
                <rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect>
                <line x1="6" y1="6" x2="6.01" y2="6"></line>
                <line x1="6" y1="18" x2="6.01" y2="18"></line>
              </svg>
            </div>
          </template>
          MCP
        </n-tooltip>
        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <div class="activity-btn" :class="{ active: activePanel === 'native_tools' }" @click="togglePanel('native_tools')">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
              </svg>
            </div>
          </template>
          Native Tools
        </n-tooltip>
      </div>
      <div class="activity-bar-bottom">
        <n-tooltip placement="right" trigger="hover">
          <template #trigger>
            <div class="activity-btn" @click="$router.push('/model_setting')">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3"></circle>
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"></path>
              </svg>
            </div>
          </template>
          模型设置
        </n-tooltip>
      </div>
    </div>

    <!-- Sidebar Area: panels overlay the session list -->
    <div class="sidebar-container">
      <!-- Skill Panel -->
      <transition name="panel-slide">
        <div class="side-panel" v-if="activePanel === 'skill'">
          <div class="side-panel-header">
            <span class="side-panel-title">Skill 面板</span>
            <div class="side-panel-actions">
              <n-button size="tiny" type="primary" class="add-entry-btn" @click="openAddChooser('skill')">
                <template #icon>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                  </svg>
                </template>
                添加
              </n-button>
              <n-button text size="tiny" @click="activePanel = null" class="close-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
              </n-button>
            </div>

          </div>
          <div class="side-panel-body">
            <n-text depth="3" style="font-size:13px;">已安装 {{ skillList.length }} 个 Skill（{{ skillToolList.length }} 个工具）</n-text>
            <div v-for="skill in skillList" :key="skill.name" class="skill-card">
              <div class="skill-card-head">
                <div style="font-size:13px; color:var(--text-primary)">{{ skill.display_name || skill.name }}</div>
                <n-button text size="tiny" type="error" @click="removeSkill(skill.name)" title="删除">×</n-button>
              </div>
              <div style="font-size:11px; color:var(--text-muted); margin-top:2px">{{ skill.description }}</div>
              <div v-if="getSkillTool(skill.name)" style="margin-top:4px; font-size:10px; color:var(--accent-300); padding-left:2px;">
                🔧 工具: skill__{{ skill.name }}
              </div>
            </div>

            <n-empty v-if="skillList.length === 0" description="暂无 Skill" size="small" style="margin-top:20px;" />
          </div>
          <div class="side-panel-footer">
            <n-button size="small" secondary block @click="refreshSkillList">刷新列表</n-button>
          </div>
        </div>
      </transition>


      <!-- Native Tools Panel -->
      <transition name="panel-slide">
        <div class="side-panel" v-if="activePanel === 'native_tools'">
          <div class="side-panel-header">
            <span class="side-panel-title">Native Tools 面板</span>
            <n-button text size="tiny" @click="activePanel = null" class="close-btn">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
            </n-button>
          </div>
          <div class="side-panel-body">
            <n-text depth="3" style="font-size:13px;">已注册 {{ nativeToolList.length }} 个内置工具</n-text>
            <div v-for="tool in nativeToolList" :key="tool.function.name" class="mcp-tool-item">
              <div class="mcp-tool-name">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0; margin-right:6px;">
                  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                </svg>
                {{ tool.function.name }}
              </div>
              <div style="font-size:11px; color:var(--text-muted); margin-top:2px; padding-left:20px;">{{ tool.function.description }}</div>
            </div>
            <n-empty v-if="nativeToolList.length === 0" description="暂无内置工具" size="small" style="margin-top:20px;" />
          </div>
        </div>
      </transition>

      <!-- MCP Panel -->
      <transition name="panel-slide">
        <div class="side-panel" v-if="activePanel === 'mcp'">
          <div class="side-panel-header">
            <span class="side-panel-title">MCP 面板</span>
            <div class="side-panel-actions">
              <n-button size="tiny" type="primary" class="add-entry-btn" @click="openAddChooser('mcp')">
                <template #icon>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
                  </svg>
                </template>
                添加
              </n-button>
              <n-button text size="tiny" @click="activePanel = null" class="close-btn">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"/></svg>
              </n-button>
            </div>

          </div>

          <div class="side-panel-body">
            <div style="font-size:12px; color:var(--text-muted); margin-bottom:10px;">
              {{ mcpServerGroups.length }} 个 Server · {{ mcpToolList.length }} 个工具
            </div>
            <!-- 每组一个可折叠 Server -->
            <div v-for="group in mcpServerGroups" :key="group.server_id" style="margin-bottom:8px;">
              <div class="mcp-server-group-header">
                <div class="mcp-server-title" @click="toggleMcpServer(group.server_id)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"
                    :style="{ transform: expandedMcpServers.has(group.server_id) ? 'rotate(90deg)' : 'rotate(0deg)', transition: 'transform 0.15s' }">
                    <polygon points="9,5 18,12 9,19"/>
                  </svg>
                  <span style="font-weight:600; margin-left:4px;">{{ group.server_id }}</span>
                  <span class="mcp-status-dot" :class="mcpStatusClass(group.server_id)" :title="mcpStatusLabel(group.server_id)"></span>
                  <span style="font-size:10px; color:var(--accent-300); margin-left:auto;">{{ group.tool_count }} 工具</span>
                </div>
                <div class="mcp-server-ops" @click.stop>
                  <n-button text size="tiny" @click="reconnectMcp(group.server_id)" title="重连">↻</n-button>
                  <n-button text size="tiny" type="error" @click="removeMcp(group.server_id)" title="删除">×</n-button>
                </div>
              </div>

              <div v-if="expandedMcpServers.has(group.server_id)" style="padding-left:12px; margin-top:4px;">
                <div v-if="group.error" style="font-size:11px; color:var(--error); padding:6px 8px;">⚠ {{ group.error }}</div>
                <div v-else v-for="tool in group.tools" :key="tool.function.name" class="mcp-tool-item">
                  <div class="mcp-tool-name">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0; margin-right:6px;">
                      <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
                    </svg>
                    {{ tool.function.name }}
                  </div>
                  <div style="font-size:11px; color:var(--text-muted); margin-top:2px; padding-left:20px;">{{ tool.function.description }}</div>
                </div>
              </div>
            </div>
            <n-empty v-if="mcpServerGroups.length === 0" description="未连接任何 MCP Server" size="small" style="margin-top:20px;" />
          </div>
          <div class="side-panel-footer">
            <n-button size="small" secondary block @click="testMcpConnection">测试连接</n-button>
          </div>
        </div>
      </transition>

      <!-- Session List (underneath, always present) -->
      <SessionList
        :sessions="sessions"
        :active-session-id="activeSessionId"
        @new-chat="newChat"
        @load-session="loadSession"
        @delete-session="deleteSession"
        @rename-session="renameSession"
      />
    </div>

    <!-- Main Chat Area -->
    <div class="chat-area">
      <!-- Welcome Screen -->
      <div class="greeting" v-if="messages.length === 0">
        <div class="greeting-icon">
          <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <path d="M8 14s1.5 2 4 2 4-2 4-2"/>
            <line x1="9" y1="9" x2="9.01" y2="9"/>
            <line x1="15" y1="9" x2="15.01" y2="9"/>
          </svg>
        </div>
        <h2 class="greeting-title">{{ greeting }}</h2>
        <p class="greeting-sub">Symbix Agent 随时为你服务</p>
        <div class="quick-actions">
          <n-button text class="quick-action" @click="sendQuick('帮我写一段代码')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
            帮我写一段代码
          </n-button>
          <n-button text class="quick-action" @click="sendQuick('解释一个概念')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
            解释一个概念
          </n-button>
          <n-button text class="quick-action" @click="sendQuick('给我一些灵感')">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>
            给我一些灵感
          </n-button>
        </div>
      </div>

      <!-- Message List -->
      <div class="message-list" ref="messageListRef" v-else>
        <ChatMessage
          v-for="(msg, idx) in messages"
          :key="idx"
          :msg="msg"
          v-show="!(msg.role === 'assistant' && msg.content === '' && loading)"
          @edit="handleEditMessage(idx, $event)"
          @approve="approveTool(idx, $event)"
          @retry="handleRetryMessage(idx)"
        />
        <div v-if="loading && messages[messages.length - 1]?.role === 'assistant'
            && messages[messages.length - 1]?.content === ''"
            class="loading-row">
          <div class="loading-bubble">
            <span class="loading-dot"></span>
            <span class="loading-dot"></span>
            <span class="loading-dot"></span>
          </div>
        </div>
      </div>

      <!-- Alert -->
      <n-alert v-if="!hasApiKey" type="warning" style="margin-bottom: 12px;" closable>
        未设置 API Key，请先配置 API 密钥
      </n-alert>

      <!-- Chat Input -->
      <ChatInput
        :loading="loading"
        :model-options="modelOptions"
        :current-model="currentModel"
        :session-id="activeSessionId"
        @send="sendMessage"
        @update:model="setModel"
        @stop="handleStopGeneration"
      />
    </div>

    <!-- 添加 Skill 弹窗：GitHub 安装 / 自定义创建 -->
    <n-modal
      v-model:show="showAddSkillModal"
      preset="card"
      title="添加 Skill"
      style="width: 480px; max-width: 94vw;"
      :bordered="false"
      class="add-modal"
    >
      <n-tabs v-model:value="skillAddMode" type="segment" size="small" style="margin-bottom: 12px;">
        <n-tab-pane name="github" tab="从 GitHub 安装" />
        <n-tab-pane name="custom" tab="自定义创建" />
      </n-tabs>
      <n-form label-placement="top" size="small">
        <template v-if="skillAddMode === 'github'">
          <n-form-item label="GitHub 仓库" required>
            <n-input v-model:value="skillForm.repo_url" placeholder="owner/repo 或 https://github.com/owner/repo" />
          </n-form-item>
          <n-form-item label="Skill 名称（可选，仓库有多个时指定）">
            <n-input v-model:value="skillForm.skill_name" placeholder="例如 my-helper" />
          </n-form-item>
          <n-form-item label="分支（可选）">
            <n-input v-model:value="skillForm.branch" placeholder="默认 main/master" />
          </n-form-item>
          <n-form-item label="覆盖已存在">
            <n-switch v-model:value="skillForm.overwrite" />
          </n-form-item>
        </template>
        <template v-else>
          <n-form-item label="Skill 名称（小写-连字符）" required>
            <n-input v-model:value="skillForm.skill_name" placeholder="例如 my-helper" />
          </n-form-item>
          <n-form-item label="显示名称">
            <n-input v-model:value="skillForm.display_name" placeholder="例如 我的助手" />
          </n-form-item>
          <n-form-item label="描述">
            <n-input v-model:value="skillForm.description" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" placeholder="简要说明用途" />
          </n-form-item>
          <n-form-item label="用途（可选）">
            <n-input v-model:value="skillForm.purpose" type="textarea" :autosize="{ minRows: 2, maxRows: 3 }" />
          </n-form-item>
          <n-form-item label="指令（可选）">
            <n-input v-model:value="skillForm.instructions" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
          </n-form-item>
        </template>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showAddSkillModal = false">取消</n-button>
          <n-button type="primary" :loading="creatingSkill" @click="submitCreateSkill">
            {{ skillAddMode === 'github' ? '安装' : '创建' }}
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- 添加 MCP 弹窗：远程 URL / 本地 npm -->
    <n-modal
      v-model:show="showAddMcpModal"
      preset="card"
      title="添加 MCP Server"
      style="width: 480px; max-width: 94vw;"
      :bordered="false"
      class="add-modal"
    >
      <n-tabs v-model:value="mcpAddMode" type="segment" size="small" style="margin-bottom: 12px;">
        <n-tab-pane name="remote" tab="远程 URL" />
        <n-tab-pane name="npm" tab="本地 npm" />
      </n-tabs>
      <n-form label-placement="top" size="small">
        <n-form-item label="Server ID" required>
          <n-input v-model:value="mcpForm.server_id" placeholder="例如 context7 / playwright" />
        </n-form-item>
        <template v-if="mcpAddMode === 'remote'">
          <n-form-item label="远程 URL" required>
            <n-input v-model:value="mcpForm.url" placeholder="https://.../sse 或 /mcp" />
          </n-form-item>
          <n-form-item label="Transport">
            <n-select
              v-model:value="mcpForm.transport"
              :options="[{ label: 'SSE', value: 'sse' }, { label: 'Streamable HTTP', value: 'streamable_http' }]"
            />
          </n-form-item>
          <n-form-item label="Headers JSON（可选）">
            <n-input
              v-model:value="mcpForm.headersText"
              type="textarea"
              :autosize="{ minRows: 2, maxRows: 4 }"
              placeholder='{"Authorization":"Bearer xxx"}'
            />
          </n-form-item>
        </template>
        <template v-else>
          <n-form-item label="npm 包名" required>
            <n-input v-model:value="mcpForm.package_name" placeholder="例如 @playwright/mcp@latest" />
          </n-form-item>
          <n-form-item label="额外参数（空格分隔，可选）">
            <n-input v-model:value="mcpForm.argsText" placeholder="例如 --headless" />
          </n-form-item>
        </template>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showAddMcpModal = false">取消</n-button>
          <n-button type="primary" :loading="installingMcp" @click="submitInstallMcp">
            {{ mcpAddMode === 'remote' ? '连接' : '安装' }}
          </n-button>
        </n-space>
      </template>
    </n-modal>

  </div>
</template>


<script setup lang="ts">
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useMessage } from 'naive-ui'
import TitleBar from '@/components/TitleBar.vue'
import SessionList from '@/components/SessionList.vue'
import ChatMessage from '@/components/ChatMessage.vue'
import ChatInput from '@/components/ChatInput.vue'
import { useSettings } from '@/composables/useSettings'
import { useApiClient } from '@/composables/useApiClient'
import { fetch } from '@tauri-apps/plugin-http'
const router = useRouter()
const messageUi = useMessage()
const { settings, loadSettings, saveSettings } = useSettings()
const { fetchModels, chatCompletion } = useApiClient()

const hello_list = ['今天想做些什么？', '欢迎回来！', '需要帮忙吗？', '有什么想聊的吗？', '又见面了！']
const greeting = hello_list[Math.floor(Math.random() * hello_list.length)]

import { useChatStore, mapBackendSteps } from '@/composables/useChatStore'
import { safeLog } from '@/utils/logMask'
const { messages, sessions, activeSessionId, persistSessions, getActiveSession } = useChatStore()
const loading = ref(false)
const messageListRef = ref<HTMLElement | null>(null)
const abortController = ref<AbortController | null>(null)
interface Skill {
  name: string
  display_name: string
  description: string
  trigger_keywords: string[]
}

const skillList = ref<Skill[]>([])
const skillToolList = ref<any[]>([])
const activePanel = ref<'skill' | 'mcp' | 'native_tools' | null>(null)
const modelOptions = ref<{ label: string; value: string }[]>([])
const currentModel = ref('gpt-4o-mini')
const mcpConfigData = ref<any>(null)
const mcpToolList = ref<{ type: string; function: { name: string; description: string; parameters: any } }[]>([])
const mcpServerGroups = ref<{ server_id: string; tool_count: number; tools: any[]; error?: string }[]>([])
const expandedMcpServers = ref<Set<string>>(new Set())
const nativeToolList = ref<{ type: string; function: { name: string; description: string; parameters: any } }[]>([])
const hasApiKey = computed(() => !!settings.value.apiKey)

// 添加 Skill / MCP 弹窗
const showAddSkillModal = ref(false)
const showAddMcpModal = ref(false)
const creatingSkill = ref(false)
const installingMcp = ref(false)
const skillAddMode = ref<'github' | 'custom'>('github')
const mcpAddMode = ref<'remote' | 'npm'>('remote')
const mcpStatusMap = ref<Record<string, { status: string; tools_count?: number; error?: string; transport?: string }>>({})
const skillForm = ref({
  skill_name: '',
  display_name: '',
  description: '',
  purpose: '',
  instructions: '',
  repo_url: '',
  branch: '',
  overwrite: false,
})
const mcpForm = ref({
  server_id: '',
  package_name: '',
  argsText: '',
  url: '',
  transport: 'sse',
  headersText: '',
})

function openAddChooser(kind: 'skill' | 'mcp') {
  if (kind === 'skill') {
    skillAddMode.value = 'github'
    showAddSkillModal.value = true
  } else {
    mcpAddMode.value = 'remote'
    showAddMcpModal.value = true
  }
}

function mcpStatusClass(serverId: string) {
  const st = mcpStatusMap.value[serverId]?.status
  if (st === 'connected') return 'ok'
  if (st === 'error') return 'err'
  return 'off'
}

function mcpStatusLabel(serverId: string) {
  const info = mcpStatusMap.value[serverId]
  if (!info) return '未知'
  if (info.status === 'connected') return `已连接 · ${info.tools_count ?? 0} 工具`
  if (info.status === 'error') return info.error || '错误'
  return info.status || '未连接'
}

async function refreshMcpStatus() {
  try {
    const res = await fetch(`${BACKEND_URL}/mcp/test`)
    if (!res.ok) return
    const data = await res.json()
    mcpStatusMap.value = data.servers || {}
  } catch {}
}

async function reconnectMcp(serverId: string) {
  try {
    const res = await fetch(`${BACKEND_URL}/mcp/servers/${encodeURIComponent(serverId)}/reconnect`, { method: 'POST' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
    if (data.connected) messageUi.success(data.message || '重连成功')
    else messageUi.warning(data.message || '已尝试重连，当前仍未连通')
    await refreshMcpPanel()
  } catch (e: any) {
    messageUi.error(`重连失败：${e.message || e}`)
  }
}

async function removeMcp(serverId: string) {
  try {
    const res = await fetch(`${BACKEND_URL}/mcp/servers/${encodeURIComponent(serverId)}`, { method: 'DELETE' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
    messageUi.success(data.message || `已删除 ${serverId}`)
    await refreshMcpPanel()
  } catch (e: any) {
    messageUi.error(`删除失败：${e.message || e}`)
  }
}

async function removeSkill(skillName: string) {
  try {
    const res = await fetch(`${BACKEND_URL}/skills/${encodeURIComponent(skillName)}`, { method: 'DELETE' })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
    messageUi.success(data.message || `已删除 ${skillName}`)
    await refreshSkillList()
  } catch (e: any) {
    messageUi.error(`删除 Skill 失败：${e.message || e}`)
  }
}



// 监听 settings 变化，同步 currentModel
watch(() => settings.value.model, (newModel) => {
  if (newModel) currentModel.value = newModel
}, { immediate: true })

// 自动持久化 sessions 到 localStorage
watch(sessions, () => {
  persistSessions()
}, { deep: true })

onMounted(async () => {
  loadSettings()
  currentModel.value = settings.value.model || 'gpt-4o-mini'
  // 尝试获取模型列表
  if (settings.value.apiKey && settings.value.baseUrl) {
    try {
      const models = await fetchModels(settings.value.apiKey, settings.value.baseUrl)
      modelOptions.value = models.map(m => ({ label: m, value: m }))
    } catch { /* silent */ }
  }
  if (modelOptions.value.length === 0 && currentModel.value) {
    modelOptions.value = [{ label: currentModel.value, value: currentModel.value }]
  }
})
async function testMcpConnection() {
  try {
    const res = await fetch('http://127.0.0.1:8000/mcp/test', {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    })
    if (res.ok) {
      const data = await res.json()
      mcpStatusMap.value = data.servers || {}
      const entries = Object.entries(mcpStatusMap.value)
      const connected = entries.filter(([, v]: any) => v?.status === 'connected').length
      if (connected > 0) {
        messageUi.success(`MCP 连接正常：${connected}/${entries.length} 个 Server 在线`)
      } else if (entries.length === 0) {
        messageUi.warning('尚未配置任何 MCP Server')
      } else {
        messageUi.warning('MCP 已配置但当前均未连通')
      }
    } else {
      messageUi.error('无法连接到 MCP 服务 (HTTP ' + res.status + ')')
    }
  } catch (err: any) {
    console.error('MCP测试连接失败:', err)
    messageUi.error('无法连接到 MCP 服务: ' + (err.message || err))
  }
}


function getSkillTool(skillName: string): any {
  return skillToolList.value.find((t: any) => t._skill_name === skillName)
}

async function refreshSkillList() {
  try {
    const res = await fetch('http://127.0.0.1:8000/skills', {
      method: 'GET',
      headers: { 'Content-Type': 'application/json' },
    })
    if (res.ok) {
      const data = await res.json()
      skillList.value = data.skills || []
      messageUi.success('Skill 列表已刷新')
    } else {
      messageUi.error('获取 Skill 列表失败 (HTTP ' + res.status + ')')
    }
  } catch (err: any) {
    console.error('获取Skill列表失败:', err)
    messageUi.error('获取 Skill 列表失败: ' + (err.message || err))
  }
  // 同时刷新 skill 工具列表
  try {
    const res = await fetch('http://127.0.0.1:8000/skills/tools')
    if (res.ok) {
      const data = await res.json()
      skillToolList.value = data.tools || []
    }
  } catch {}
}
async function togglePanel(panel: 'skill' | 'mcp' | 'native_tools') {
  console.log('🟡 togglePanel called', panel)
  // 如果当前已经是激活状态，点击则是关闭，不需要请求
  if (activePanel.value === panel) {
    activePanel.value = null
    return
  }

  activePanel.value = panel

  // 根据打开的面板动态请求后端 FastAPI
  if (panel === 'skill') {
    try {
      // 对应你的 FastAPI: @app.get("/skills")
      const res = await fetch('http://127.0.0.1:8000/skills')
      const data = await res.json()
      skillList.value = data.skills
    } catch (err) {
      console.log("具体错误为：",err)
      messageUi.error('获取 Skill 列表失败')
    }
  } else if (panel === 'native_tools') {
    try {
      const res = await fetch('http://127.0.0.1:8000/native/tools')
      const data = await res.json()
      nativeToolList.value = data.tools || []
    } catch (err) {
      console.log("获取 Native Tools 列表失败:", err)
      messageUi.error('获取 Native Tools 列表失败')
    }
  } else if (panel === 'mcp') {
    try {
      const res = await fetch('http://127.0.0.1:8000/mcp/config')
      mcpConfigData.value = await res.json()
    } catch (err) {
      console.log("具体错误为：",err)
      messageUi.error('获取 MCP 配置失败')
    }
    try {
      const res = await fetch('http://127.0.0.1:8000/mcp/tools')
      const data = await res.json()
      mcpToolList.value = data.tools || []
    } catch (err) {
      console.log("获取MCP工具列表失败:", err)
    }
    // 按 server 分组获取 + 状态
    await refreshMcpPanel()
  }
}


function toggleMcpServer(serverId: string) {
  const s = new Set(expandedMcpServers.value)
  if (s.has(serverId)) {
    s.delete(serverId)
  } else {
    s.add(serverId)
  }
  expandedMcpServers.value = s
}
function handleStopGeneration() {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  loading.value = false
}

function handleEditMessage(idx: number, newText: string) {
  // 截断到该消息位置，替换为新文本并重新发送
  messages.value.splice(idx)
  loading.value = false
  sendMessage(newText, [])
}

/** 重试 assistant 回复：找到对应 user 消息，截断后重新发送 */
function handleRetryMessage(idx: number) {
  if (loading.value) return
  if (idx <= 0 || messages.value[idx]?.role !== 'assistant') return

  // 向前找到触发该回复的 user 消息
  let userIdx = idx - 1
  while (userIdx >= 0 && messages.value[userIdx].role !== 'user') {
    userIdx--
  }
  if (userIdx < 0) return

  const userText = messages.value[userIdx].content
  // 从 user 消息起截断（含 assistant 及之后），由 sendMessage 重新推入
  messages.value.splice(userIdx)
  loading.value = false
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  sendMessage(userText, [])
}

function setModel(model: string) {
  currentModel.value = model
  saveSettings({ model })
}

function newChat() {
  // 清空当前对话区；真正创建会话在首次 sendMessage 时
  messages.value = []
  activeSessionId.value = null
}

function loadSession(id: string) {
  const session = sessions.value.find(s => s.id === id)
  if (!session) return
  activeSessionId.value = id
  messages.value = [...session.messages]
  nextTick(() => scrollToBottom())
}

async function deleteSession(id: string) {
  const idx = sessions.value.findIndex(s => s.id === id)
  if (idx < 0) return
  const session = sessions.value[idx]

  sessions.value.splice(idx, 1)
  if (activeSessionId.value === id) {
    messages.value = []
    activeSessionId.value = null
  }

  // 按 session id 删除后端 Markdown
  try {
    await fetch(`${BACKEND_URL}/api/delete_markdown`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: id, title: session.title }),
    })
  } catch (err) {
    console.error('删除 MD 文件失败:', err)
  }
}

async function renameSession(id: string, newTitle: string) {
  const session = sessions.value.find(s => s.id === id)
  if (!session || !newTitle.trim()) return
  const oldTitle = session.title
  session.title = newTitle.trim()
  session.titleGenerated = true // 用户手动改过，不再自动生成
  try {
    await fetch(`${BACKEND_URL}/api/rename_session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: id, title: session.title, old_title: oldTitle }),
    })
  } catch (err) {
    console.error('重命名失败:', err)
  }
}

function sendQuick(text: string) {
  sendMessage(text, [])
}

const BACKEND_URL = 'http://127.0.0.1:8000'

async function sendMessage(text: string, files: any[]) {
  console.log('=== sendMessage 开始（SSE 流式）===')
  safeLog('settings:', settings.value)

  let displayContent = text
  const ready = (files || []).filter((f: any) => f && (f.path || f.name))
  if (ready.length > 0) {
    const fileNames = ready.map((f: any) => `[文件: ${f.name || f.filename || 'file'}]`).join(' ')
    displayContent = text ? `${fileNames}\n${text}` : fileNames
  }

  messages.value.push({ role: 'user', content: displayContent })

  // 新对话首轮：创建带 UUID 的 session，并激活
  if (!activeSessionId.value) {
    const newId = crypto.randomUUID()
    const title = displayContent.slice(0, 20).replace(/[\\/:*?"<>|]/g, '') || '新对话'
    sessions.value.unshift({
      id: newId,
      title,
      messages: [...messages.value],
      titleGenerated: false,
    })
    activeSessionId.value = newId
  } else {
    const session = sessions.value.find(s => s.id === activeSessionId.value)
    if (session) session.messages = [...messages.value]
  }

  const currentSessionId = activeSessionId.value!

  loading.value = true
  await nextTick()
  scrollToBottom()
  let assistantMsgIndex = -1
  try {
    assistantMsgIndex = messages.value.push({ role: 'assistant', content: '' }) - 1
    const assistantMsg = messages.value[assistantMsgIndex] as any

    const attachments = ready.map((f: any) => ({
      path: f.path || '',
      filename: f.name || f.filename || '',
      name: f.name || f.filename || '',
      mime: f.mime || f.type || '',
      type: f.mime || f.type || '',
      size: f.size || 0,
    }))
    const requestBody = {
      message: text || '',
      session_id: currentSessionId,
      system_prompt: settings.value.systemPrompt || '',
      api_key: settings.value.apiKey || '',
      api_base: settings.value.baseUrl || '',
      model: settings.value.model || currentModel.value,
      use_mcp: true,
      attachments,
    }

    abortController.value = new AbortController()
    const response = await fetch(`${BACKEND_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requestBody),
      signal: abortController.value.signal,
    })

    if (!response.ok) {
      const errText = await response.text()
      throw new Error(`HTTP ${response.status}: ${errText}`)
    }

    // ─── 读取 SSE 流 ────────────────────────────────────────
    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let done = false
    const steps: any[] = []
    const toolCallAcc: Record<number, string> = {} // index → args 累积

    while (!done) {
      const { value, done: readerDone } = await reader.read()
      if (readerDone) break
      buffer += decoder.decode(value, { stream: true })

      // 按行解析 SSE
      const lines = buffer.split('\n')
      buffer = lines.pop() || '' // 保留不完整的最后一行

      let currentEventType = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEventType = line.slice(7).trim()
          continue
        }
        if (line.startsWith('data: ')) {
          const dataStr = line.slice(6)
          if (dataStr === '[DONE]') {
            done = true
            break
          }
          try {
            const evt = JSON.parse(dataStr)
            handleSSEEvent(evt, currentEventType, assistantMsg, steps, toolCallAcc)
          } catch {
            // 跳过无法解析的数据
          }
          currentEventType = ''
        }
      }

      // 如果是 await_approval 之后就 break
      if (assistantMsg.approval_id) {
        done = true
        break
      }
    }

    loading.value = false
    abortController.value = null
    // 同步当前会话消息，避免侧边栏停留在旧内容
    const active = sessions.value.find(s => s.id === currentSessionId)
    if (active) active.messages = [...messages.value]
    await saveSessionToLocalMarkdown()

  } catch (e: any) {
    loading.value = false
    abortController.value = null
    if (e.name === 'AbortError') {
      console.log('=== 流被用户中断 ===')
      if (assistantMsgIndex !== -1 && !messages.value[assistantMsgIndex]?.content) {
        messages.value.splice(assistantMsgIndex, 1)
      }
      return
    }
    console.error('=== 流式异常 ===', e)
    if (assistantMsgIndex !== -1 && !messages.value[assistantMsgIndex]?.content) {
      messages.value.splice(assistantMsgIndex, 1)
    } else if (assistantMsgIndex !== -1) {
      messages.value[assistantMsgIndex].content += `\n\n[错误] ${e.message}`
    }
    messageUi.error(`请求失败：${e.message}`)
  }
}


/**
 * 处理单条 SSE 事件，更新 assistant 消息。
 */
function handleSSEEvent(
  evt: any,
  eventType: string,
  msg: any,
  steps: any[],
  toolCallAcc: Record<number, string>,
) {
  const type = evt.type || eventType

  switch (type) {
    case 'delta':
      msg.content += evt.content || ''
      nextTick(() => scrollToBottom())
      break

    case 'reasoning':
      msg.reasoning = (msg.reasoning || '') + (evt.content || '')
      break

    case 'tool_call': {
      // 工具调用分片：增量追加参数
      const idx = steps.length // 简单 index — 后端每个 content_block 唯一
      const id = evt.id || ''
      const name = evt.name || ''
      const argsChunk = evt.arguments || ''
      if (!toolCallAcc[idx]) {
        toolCallAcc[idx] = argsChunk
        steps.push({ id, name, arguments: argsChunk, status: 'pending' })
      } else {
        toolCallAcc[idx] += argsChunk
        const found = steps.find((s: any) => s.id === id)
        if (found) found.arguments = toolCallAcc[idx]
      }
      msg.steps = steps.map((s: any) => ({
        ...s,
        arguments: typeof s.arguments === 'string' ? s.arguments : JSON.stringify(s.arguments ?? {}),
      }))
      nextTick(() => scrollToBottom())
      break
    }

    case 'tool_result': {
      const target = steps.find((s: any) => s.id === evt.id)
      if (target) {
        target.result = evt.content || ''
        target.status = 'done'
      } else {
        steps.push({
          id: evt.id || '',
          name: evt.name || '(result)',
          arguments: '',
          result: evt.content || '',
          status: 'done',
        })
      }
      msg.steps = steps.map((s: any) => ({
        ...s,
        arguments: typeof s.arguments === 'string' ? s.arguments : JSON.stringify(s.arguments ?? {}),
      }))
      nextTick(() => scrollToBottom())
      break
    }

    case 'steps': {
      const backendSteps = evt.steps || []
      msg.steps = mapBackendSteps(backendSteps, undefined)
      nextTick(() => scrollToBottom())
      break
    }

    case 'await_approval':
      msg.approval_id = evt.approval_id
      if (msg.steps && msg.steps.length > 0) {
        const pendingStep = msg.steps.find((s: any) => s.name === (evt.tool?.name))
        if (pendingStep) pendingStep.status = 'awaiting_approval'
      }
      break

    case 'done':
      // done 的 content 是完整文本，覆盖（防止分片遗漏）
      if (evt.content && evt.content !== msg.content) {
        msg.content = evt.content
      }
      if (evt.reasoning) msg.reasoning = evt.reasoning
      if (evt.tool_calls) {
        const mapped = evt.tool_calls.map((tc: any) => ({
          id: tc.id,
          name: tc.name,
          arguments: tc.arguments,
          status: 'done',
        }))
        msg.steps = mapped
      }
      break

    case 'error':
      msg.content += `\n\n[错误] ${evt.content || ''}`
      break
  }
}
// 将当前 Session 保存为本地 MD 文件
async function saveSessionToLocalMarkdown() {
  if (messages.value.length === 0 || !activeSessionId.value) return

  try {
    await fetch(`${BACKEND_URL}/api/save_markdown`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: activeSessionId.value,
        title: messages.value[0].content.slice(0, 20).replace(/[\\/:*?"<>|]/g, '') || 'untitled',
        history: messages.value.map(m => ({ role: m.role, content: m.content })),
      }),
    })
    console.log('历史记录已保存为 Markdown')

    // 新会话首次保存后，异步生成 AI 标题
    const session = sessions.value.find(s => s.id === activeSessionId.value)
    if (session && !session.titleGenerated) {
      tryGenerateTitle(session.id)
    }
  } catch (err) {
    console.error('保存 MD 文件失败:', err)
  }
}

/** 异步调用后端 AI 生成标题 */
async function tryGenerateTitle(sessionId: string) {
  const session = sessions.value.find(s => s.id === sessionId)
  if (!session || session.titleGenerated) return

  // 取对话前 3 轮作为上下文
  const recent = session.messages.slice(0, 6).map(m => `${m.role}: ${m.content.slice(0, 200)}`).join('\n')
  try {
    const res = await fetch(`${BACKEND_URL}/api/generate_title`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: sessionId,
        context: recent,
      }),
    })
    if (res.ok) {
      const data = await res.json()
      if (data.title) {
        session.title = data.title
        session.titleGenerated = true
      }
    }
  } catch (err) {
    console.error('生成标题失败:', err)
  }
}
async function installMcpServer(packageName: string, serverId: string, args: string[] = []) {
  const res = await fetch('http://127.0.0.1:8000/mcp/install/npm', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ package_name: packageName, server_id: serverId, args })
  })
  if (!res.ok) {
    const errText = await res.text()
    throw new Error(errText || `HTTP ${res.status}`)
  }
  const data = await res.json()
  if (data.status && data.status !== 'ok') {
    throw new Error(data.message || data.detail || '安装失败')
  }
  return data
}

async function refreshMcpPanel() {
  try {
    const res = await fetch('http://127.0.0.1:8000/mcp/config')
    if (res.ok) mcpConfigData.value = await res.json()
  } catch {}
  try {
    const res = await fetch('http://127.0.0.1:8000/mcp/tools')
    if (res.ok) {
      const data = await res.json()
      mcpToolList.value = data.tools || []
    }
  } catch {}
  try {
    const res = await fetch('http://127.0.0.1:8000/mcp/tools/by_server')
    if (res.ok) {
      const data = await res.json()
      mcpServerGroups.value = data.servers || []
      // 合并配置中尚未连接的 server
      const cfgServers = mcpConfigData.value?.mcpServers || {}
      for (const id of Object.keys(cfgServers)) {
        if (!mcpServerGroups.value.find(g => g.server_id === id)) {
          mcpServerGroups.value.push({ server_id: id, tool_count: 0, tools: [], error: '未连接' })
        }
      }
      expandedMcpServers.value.clear()
      if (mcpServerGroups.value.length > 0) {
        expandedMcpServers.value.add(mcpServerGroups.value[0].server_id)
      }
    }
  } catch {}
  await refreshMcpStatus()
}

async function submitCreateSkill() {
  creatingSkill.value = true
  try {
    if (skillAddMode.value === 'github') {
      const repo = skillForm.value.repo_url.trim()
      if (!repo) {
        messageUi.warning('请填写 GitHub 仓库地址')
        return
      }
      const res = await fetch(`${BACKEND_URL}/skills/install/github`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          repo_url: repo,
          skill_name: skillForm.value.skill_name.trim(),
          branch: skillForm.value.branch.trim(),
          overwrite: !!skillForm.value.overwrite,
        }),
      })
      if (!res.ok) {
        let detail = `HTTP ${res.status}`
        try {
          const err = await res.json()
          detail = err.detail || err.message || detail
        } catch {
          detail = await res.text() || detail
        }
        throw new Error(detail)
      }
      const data = await res.json()
      messageUi.success(data.message || 'Skill 安装成功')
    } else {
      const name = skillForm.value.skill_name.trim()
      if (!name) {
        messageUi.warning('请填写 Skill 名称')
        return
      }
      const res = await fetch(`${BACKEND_URL}/skills/create`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          skill_name: name,
          display_name: skillForm.value.display_name.trim(),
          description: skillForm.value.description.trim(),
          purpose: skillForm.value.purpose.trim(),
          instructions: skillForm.value.instructions.trim(),
          overwrite: !!skillForm.value.overwrite,
        }),
      })
      if (!res.ok) {
        let detail = `HTTP ${res.status}`
        try {
          const err = await res.json()
          detail = err.detail || err.message || detail
        } catch {
          detail = await res.text() || detail
        }
        throw new Error(detail)
      }
      const data = await res.json()
      messageUi.success(data.message || `Skill '${name}' 已创建`)
    }
    showAddSkillModal.value = false
    skillForm.value = {
      skill_name: '', display_name: '', description: '', purpose: '', instructions: '',
      repo_url: '', branch: '', overwrite: false,
    }
    await refreshSkillList()
  } catch (e: any) {
    messageUi.error(`安装/创建失败：${e.message || e}`)
  } finally {
    creatingSkill.value = false
  }
}

async function submitInstallMcp() {
  const serverId = mcpForm.value.server_id.trim()
  if (!serverId) {
    messageUi.warning('请填写 Server ID')
    return
  }
  installingMcp.value = true
  try {
    if (mcpAddMode.value === 'remote') {
      const url = mcpForm.value.url.trim()
      if (!url) {
        messageUi.warning('请填写远程 MCP URL')
        return
      }
      let headers: Record<string, string> = {}
      const ht = mcpForm.value.headersText.trim()
      if (ht) {
        try {
          headers = JSON.parse(ht)
        } catch {
          messageUi.warning('Headers 需为合法 JSON，例如 {"Authorization":"Bearer xxx"}')
          return
        }
      }
      const res = await fetch(`${BACKEND_URL}/mcp/servers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server_id: serverId,
          url,
          transport: mcpForm.value.transport || 'sse',
          headers,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
      if (data.connected) messageUi.success(data.message || '远程 MCP 已连接')
      else messageUi.warning(data.message || '配置已保存，但当前未连通（可能需要鉴权后重连）')
    } else {
      const packageName = mcpForm.value.package_name.trim()
      if (!packageName) {
        messageUi.warning('请填写 npm 包名')
        return
      }
      const args = mcpForm.value.argsText.trim().split(/\s+/).filter(Boolean)
      const res = await fetch(`${BACKEND_URL}/mcp/servers`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          server_id: serverId,
          package_name: packageName,
          args,
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
      if (data.connected) messageUi.success(data.message || `MCP '${serverId}' 已添加`)
      else messageUi.warning(data.message || '已添加但启动失败')
    }
    showAddMcpModal.value = false
    mcpForm.value = { server_id: '', package_name: '', argsText: '', url: '', transport: 'sse', headersText: '' }
    await refreshMcpPanel()
  } catch (e: any) {
    messageUi.error(`添加失败：${e.message || e}`)
  } finally {
    installingMcp.value = false
  }
}


// 工具审批：用户在 ChatMessage 卡片点击 同意/拒绝 后回调
async function approveTool(msgIdx: number, approved: boolean) {
  const msg: any = messages.value[msgIdx]
  if (!msg || !msg.approval_id) return
  loading.value = true
  try {
    const res = await fetch(`${BACKEND_URL}/chat/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        approval_id: msg.approval_id,
        approved,
        session_id: activeSessionId.value || 'default',
        system_prompt: settings.value.systemPrompt || '',
        api_key: settings.value.apiKey || '',
        api_base: settings.value.baseUrl || '',
        model: settings.value.model || currentModel.value,
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const steps = mapBackendSteps(data.steps || [], data.pending_tool)

    if (data.status === 'pending_approval') {
      msg.reasoning = data.reasoning
      msg.steps = steps
      msg.approval_id = data.approval_id
      msg.content = ''
      loading.value = false
      return
    }

    msg.content = data.content || data.response || data.message || data.text || ''
    msg.reasoning = data.reasoning
    msg.steps = steps
    msg.approval_id = undefined
    loading.value = false
    await saveSessionToLocalMarkdown()
  } catch (e: any) {
    loading.value = false
    console.error('审批失败:', e)
    messageUi.error(`审批失败：${e.message}`)
  }
}

function scrollToBottom() {
  if (messageListRef.value) {
    messageListRef.value.scrollTop = messageListRef.value.scrollHeight
  }
}
</script>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  background: var(--bg-app);
  color: var(--text-primary);
  padding-top: 32px;
  overflow: hidden;
}

/* ---- Activity Bar (VSCode-style) ---- */
.activity-bar {
  width: 48px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  background: var(--activity-bar-bg);
  backdrop-filter: blur(12px);
  border-right: 1px solid var(--border);
  flex-shrink: 0;
  z-index: 10;
}
.activity-bar-top {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.activity-bar-bottom {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  margin-top: auto;
  padding-bottom: 8px;
}
.activity-btn {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md, 8px);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--duration-base, 180ms) var(--ease-standard, ease);
  position: relative;
  transform: translateY(-15px);
}
.activity-btn:hover {
  color: var(--text-primary);
  background: var(--surface-hover);
}
.activity-btn.active {
  color: var(--accent-500, #EF6B6E);
  background: var(--accent-soft);
}
.activity-btn.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 2px;
  background: var(--symbix-gradient-soft, linear-gradient(135deg, #F7A85B 0%, #E85C93 100%));
  border-radius: 0 2px 2px 0;
}

/* ---- Sidebar Container ---- */
.sidebar-container {
  position: relative;
  flex-shrink: 0;
}

/* ---- Side Panel (Skill / MCP) ---- */
.side-panel {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 260px;
  background: var(--panel-bg);
  backdrop-filter: blur(16px);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  z-index: 20;
  box-shadow: var(--shadow-md, 0 4px 12px rgba(0, 0, 0, 0.18));
}

/* Panel slide transition */
.panel-slide-enter-active {
  transition: all var(--duration-base, 180ms) var(--ease-standard, ease);
}
.panel-slide-leave-active {
  transition: all var(--duration-fast, 120ms) var(--ease-standard, ease);
}
.panel-slide-enter-from {
  opacity: 0;
  transform: translateX(-20px);
}
.panel-slide-leave-to {
  opacity: 0;
  transform: translateX(-12px);
}
.side-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}
.side-panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.side-panel-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.add-entry-btn {
  font-weight: 600 !important;
}
.skill-card {
  margin-top: 8px;
  padding: 8px;
  border-radius: 8px;
  background: var(--surface-hover);
}
.skill-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.mcp-server-group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 8px 10px;
  border-radius: var(--radius-md, 8px);
  background: var(--accent-soft);
  color: var(--text-secondary);
  font-size: 12px;
  user-select: none;
}
.mcp-server-title {
  display: flex;
  align-items: center;
  flex: 1;
  min-width: 0;
  cursor: pointer;
}
.mcp-server-ops {
  display: flex;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
}
.mcp-status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  margin-left: 6px;
  background: #888;
  flex-shrink: 0;
}
.mcp-status-dot.ok { background: #22c55e; box-shadow: 0 0 6px rgba(34,197,94,0.55); }
.mcp-status-dot.err { background: #ef4444; }
.mcp-status-dot.off { background: #9ca3af; }
.close-btn {
  color: var(--text-muted) !important;
}
.close-btn:hover {
  color: var(--text-secondary) !important;
}


.side-panel-body {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
}
.side-panel-body:hover {
  scrollbar-color: var(--scrollbar) transparent;
}
.side-panel-body::-webkit-scrollbar {
  width: 4px;
}
.side-panel-body::-webkit-scrollbar-track {
  background: transparent;
}
.side-panel-body::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 4px;
}
.side-panel-body:hover::-webkit-scrollbar-thumb {
  background: var(--scrollbar);
}
.side-panel-body::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-hover);
}
.mcp-tool-item {
  margin-top: 8px;
  padding: 8px;
  border-radius: var(--radius-md);
  background: var(--surface-hover);
  border: 1px solid transparent;
}
.mcp-tool-name {
  font-size: 13px;
  color: var(--accent-300, #F7A85B);
  display: flex;
  align-items: center;
}
.mcp-server-group-header {
  transition: background var(--duration-fast) ease;
}
.mcp-server-group-header:hover {
  background: var(--accent-soft-hover);
}



/* ---- Side Panel Footer (固定底部按钮区) ---- */
.side-panel-footer {
  flex-shrink: 0;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
}

/* ---- Chat Area ---- */
.chat-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 18px 24px 28px;
  overflow: hidden;
  min-width: 0;
}

/* ---- Welcome / Greeting ---- */
.greeting {
  text-align: center;
  margin: auto;
  padding-bottom: 60px;
  display: flex;
  flex-direction: column;
  align-items: center;
  animation: fadeUp 0.5s var(--ease-standard, ease);
}
@keyframes fadeUp {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
.greeting-icon {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  background: var(--accent-soft);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
  color: var(--accent-500, #EF6B6E);
}
.greeting-title {
  font-size: 24px;
  font-weight: 600;
  background: var(--symbix-gradient, linear-gradient(135deg, #F7A85B 0%, #F2657A 55%, #E85C93 100%));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin: 0 0 8px;
}
.greeting-sub {
  font-size: 14px;
  color: var(--text-secondary);
  margin: 0 0 32px;
}
.quick-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: center;
}
.quick-action {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px !important;
  border-radius: var(--radius-full) !important;
  border: 1px solid var(--border) !important;
  color: var(--text-secondary) !important;
  font-size: 13px !important;
  transition: all var(--duration-base) var(--ease-standard);
}
.quick-action:hover {
  border-color: var(--accent-border) !important;
  color: var(--text-primary) !important;
  background: var(--accent-soft) !important;
  transform: translateY(-1px);
}

/* ---- Message List ---- */
.message-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding-right: 4px;
  padding-bottom: 16px;
  scroll-behavior: smooth;
}
.message-list::-webkit-scrollbar {
  width: 5px;
}
.message-list::-webkit-scrollbar-track {
  background: transparent;
}
.message-list::-webkit-scrollbar-thumb {
  background: var(--scrollbar);
  border-radius: 3px;
}
.message-list::-webkit-scrollbar-thumb:hover {
  background: var(--scrollbar-hover);
}

/* ---- Loading ---- */
.loading-row {
  display: flex;
  justify-content: flex-start;
  margin: 4px 0;
}
.loading-bubble {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 12px 18px;
  border-radius: var(--radius-md, 8px);
  border-bottom-left-radius: 4px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
}
.loading-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-500, #EF6B6E);
  animation: bounce 1.4s ease-in-out infinite;
}
.loading-dot:nth-child(1) { animation-delay: 0s; }
.loading-dot:nth-child(2) { animation-delay: 0.2s; }
.loading-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}
</style>
