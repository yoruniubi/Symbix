import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const projectRoot = resolve(import.meta.dirname, '..')
const chatWindowPath = resolve(projectRoot, 'src/pages/chat_window.vue')

const requirements = [
  ['src/components/panels/SkillPanel.vue', '<SkillPanel', 'update:activePanel'],
  ['src/components/panels/McpPanel.vue', '<McpPanel', 'testMcpConnection'],
  ['src/components/panels/NativeToolsPanel.vue', '<NativeToolsPanel', 'update:activePanel'],
  ['src/components/ChatWelcome.vue', '<ChatWelcome', 'quickSend'],
  ['src/components/AddSkillModal.vue', '<AddSkillModal', "(e: 'submit')"],
  ['src/components/AddMcpModal.vue', '<AddMcpModal', "(e: 'submit')"],
  ['src/components/ChatActivityBar.vue', '<ChatActivityBar', "(e: 'toggle'"],
]

const failures = []
const chatWindow = readFileSync(chatWindowPath, 'utf8')

for (const [relativePath, componentTag, emittedEvent] of requirements) {
  const componentPath = resolve(projectRoot, relativePath)
  if (!existsSync(componentPath)) {
    failures.push(`Missing component: ${relativePath}`)
    continue
  }

  const componentSource = readFileSync(componentPath, 'utf8')
  if (!chatWindow.includes(componentTag)) failures.push(`chat_window.vue does not render ${componentTag}`)
  if (!componentSource.includes(emittedEvent)) failures.push(`${relativePath} does not declare ${emittedEvent}`)
}

for (const marker of ['<template>', '</template>', '<script setup lang="ts">', '</script>']) {
  if (!chatWindow.includes(marker)) failures.push(`chat_window.vue is missing ${marker}`)
}

for (const obsoleteMarker of [
  '<!-- Native Tools Panel -->',
  '<div class="greeting" v-if="messages.length === 0">',
  'v-model:show="showAddSkillModal"',
  'v-model:show="showAddMcpModal"',
  '<!-- VSCode-style Activity Bar -->',
]) {
  if (chatWindow.includes(obsoleteMarker)) failures.push(`Obsolete inline markup remains: ${obsoleteMarker}`)
}

if (failures.length) {
  console.error('chat_window split validation failed:')
  for (const failure of failures) console.error(`- ${failure}`)
  process.exit(1)
}

console.log('chat_window split validation passed.')
