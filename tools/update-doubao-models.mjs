// 拉取火山方舟模型目录，筛出可聊天的模型，生成 DSH provider 的 models 列表。
// 用法：node tools/update-doubao-models.mjs [--write]
import { readFileSync, writeFileSync, copyFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { homedir } from 'node:os'

const HERE = dirname(fileURLToPath(import.meta.url))
const PKG = dirname(HERE)
const BASE = 'https://ark.cn-beijing.volces.com/api/v3'
const CRED = join(homedir(), '.dsh', '.credentials.yaml')
const PATCH = join(homedir(), '.dsh', 'profiles', 'desktop', 'cordis.patch.yml')

const credText = readFileSync(CRED, 'utf8')
const key = (credText.match(/ARK_DOUBAO_API_KEY:\s*(\S+)/) || [])[1]
if (!key) {
  console.error('没找到 ARK_DOUBAO_API_KEY')
  process.exit(1)
}

const res = await fetch(`${BASE}/models`, { headers: { Authorization: `Bearer ${key}` } })
if (!res.ok) {
  console.error('拉模型列表失败：' + res.status)
  process.exit(1)
}
const data = await res.json()
const all = Array.isArray(data.data) ? data.data : []

const chat = all.filter((m) => {
  const api = m.api_supported || {}
  const canChat = Boolean(api['chat/completions'] || api['batch/chat/completions'] || api.messages || api.responses)
  if (!canChat) return false
  // 只保留可发布/在役的
  if (m.status && m.status !== 'Published') return false
  return true
})

const inputsOf = (m) => {
  // 关键：DSH 的 pi-ai 适配器只接受 text / image 两种模态，
  // 写 video / audio 会让整条 provider 校验失败、界面上直接不出现。
  const list = (m.modalities?.input_modalities || ['text']).filter((x) => ['text', 'image'].includes(x))
  return list.length ? list : ['text']
}

console.log(`目录共 ${all.length} 个，可聊天 ${chat.length} 个：`)
for (const m of chat) {
  console.log(`- ${m.id}  [${inputsOf(m).join(',')}]  ctx=${Math.round((m.context_window || 0) / 1024)}k  ${m.status}`)
}

// 只写豆包系 + 几个明显想给人用的第三方旗舰？先全量，按 id 排序
const models = chat
  .slice()
  .sort((a, b) => a.id.localeCompare(b.id))
  .map((m) => ({ id: m.id, input: inputsOf(m) }))

const block = ['        models:', ...models.flatMap((m) => [
  `        - id: ${m.id}`,
  '          input:',
  ...m.input.map((x) => `          - ${x}`),
])].join('\n')

if (!process.argv.includes('--write')) {
  console.log('\n预览（加 --write 才写入）：\n' + block)
  process.exit(0)
}

const text = readFileSync(PATCH, 'utf8')
const start = text.indexOf('      doubao-ark:')
if (start < 0) {
  console.error('配置里没有 doubao-ark')
  process.exit(1)
}
const modelsAt = text.indexOf('        models:', start)
const displayAt = text.indexOf('        displayName:', modelsAt)
if (modelsAt < 0 || displayAt < 0) {
  console.error('配置结构不符，未写入')
  process.exit(1)
}
const next = text.slice(0, modelsAt) + block + '\n' + text.slice(displayAt)
copyFileSync(PATCH, PATCH + '.bak-models-' + new Date().toISOString().replace(/[:.]/g, '-'))
writeFileSync(PATCH, next, 'utf8')
console.log(`\n已写入 ${models.length} 个模型到 ${PATCH}`)
