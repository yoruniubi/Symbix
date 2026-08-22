// MCP 工具静态映射表（可选，不强制覆盖所有工具）
// 为常见 MCP 工具预定义中文名 + 描述 + SVG icon
// 新 MCP 工具可以手动添加到这里，或者通过运行时翻译 fallback

export interface McpToolI18n {
  name: string
  description: string
  icon?: string // 可选，用专属 icon key
}

export const MCP_TOOL_I18N: Record<string, McpToolI18n> = {
  // GitHub
  'mcp__github__create_issue': {
    name: '创建 Issue',
    description: '在 GitHub 仓库中创建一个新的 Issue',
    icon: 'github',
  },
  'mcp__github__list_issues': {
    name: '列出 Issues',
    description: '列出 GitHub 仓库中的 Issues',
    icon: 'github',
  },
  'mcp__github__create_pull_request': {
    name: '创建 PR',
    description: '在 GitHub 仓库中创建一个新的 Pull Request',
    icon: 'github',
  },
  'mcp__github__search_repositories': {
    name: '搜索仓库',
    description: '在 GitHub 上搜索仓库',
    icon: 'github',
  },
  // Slack
  'mcp__slack__send_message': {
    name: '发送消息',
    description: '在 Slack 频道中发送消息',
    icon: 'slack',
  },
  'mcp__slack__list_channels': {
    name: '列出频道',
    description: '列出 Slack 工作区中的频道',
    icon: 'slack',
  },
  // Filesystem
  'mcp__filesystem__read_file': {
    name: '读取文件',
    description: '读取文件内容',
    icon: 'file',
  },
  'mcp__filesystem__write_file': {
    name: '写入文件',
    description: '写入内容到文件',
    icon: 'file',
  },
  'mcp__filesystem__list_directory': {
    name: '列出目录',
    description: '列出目录中的文件和子目录',
    icon: 'folder',
  },
  // Web
  'mcp__web__search': {
    name: '搜索网页',
    description: '在网页上搜索内容',
    icon: 'search',
  },
  'mcp__web__fetch': {
    name: '获取网页',
    description: '获取网页内容',
    icon: 'globe',
  },
  // Database
  'mcp__database__query': {
    name: '查询数据库',
    description: '执行数据库查询',
    icon: 'database',
  },
  'mcp__database__execute': {
    name: '执行 SQL',
    description: '执行 SQL 语句',
    icon: 'database',
  },
}

export function getMcpToolI18n(toolName: string): McpToolI18n | null {
  return MCP_TOOL_I18N[toolName] || null
}

export function hasMcpToolI18n(toolName: string): boolean {
  return toolName in MCP_TOOL_I18N
}
