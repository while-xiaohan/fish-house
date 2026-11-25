// 把 fish-house-bridge 装进鲸鲸：生成 flow.json + 授权文件，并打开 javascriptPlugins 开关。
// 用法：node tools/install-whale.mjs [--uninstall]
import { createHash } from 'node:crypto'
import { copyFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const PKG = dirname(HERE)
const WG = process.env.WHALE_HOME || 'E:\\AI\\WhaleGirl'
const pluginsDir = join(WG, 'data', 'plugins')
const id = 'fish-house-bridge'
const flowFile = join(pluginsDir, id + '.flow.json')
const grantFile = join(pluginsDir, id + '.flow-grant.json')
const enabledFile = join(pluginsDir, id + '.enabled')
const srcFile = join(PKG, 'whale-plugin', 'fish-house-bridge.js')
const configFile = join(WG, 'data', 'config.json')

const uninstall = process.argv.includes('--uninstall')

if (!existsSync(pluginsDir)) {
  console.error('没有找到鲸鲸插件目录：' + pluginsDir)
  process.exit(1)
}

if (uninstall) {
  for (const file of [flowFile, grantFile, enabledFile]) {
    try { if (existsSync(file)) { writeFileSync(file, ''); } } catch { /* ignore */ }
  }
  console.log('已清空插件文件（保留空文件避免鲸鲸报错）')
  process.exit(0)
}

const source = readFileSync(srcFile, 'utf8')
const flow = {
  id,
  api: 4,
  kind: 'message',
  hooks: ['chat.received', 'chat.dispatched'],
  permissions: ['system.full'],
  executionTimeoutMs: 3000,
  javascript: source,
}
const json = JSON.stringify(flow)
writeFileSync(flowFile, json, 'utf8')

const hash = createHash('sha256').update(Buffer.from(json, 'utf8')).digest('hex')
writeFileSync(grantFile, JSON.stringify({ hash, enabled: true, fullAccess: true, settings: {} }), 'utf8')
writeFileSync(enabledFile, '1', 'utf8')
console.log('已写入插件：' + flowFile)

// 打开 features.javascriptPlugins
try {
  const raw = readFileSync(configFile, 'utf8')
  const cfg = JSON.parse(raw)
  cfg.features = cfg.features || {}
  if (cfg.features.javascriptPlugins !== true) {
    copyFileSync(configFile, configFile + '.bak-fish-house')
    cfg.features.javascriptPlugins = true
    writeFileSync(configFile, JSON.stringify(cfg, null, 2), 'utf8')
    console.log('已打开 features.javascriptPlugins（重载内核后生效）')
  } else {
    console.log('features.javascriptPlugins 已经是打开的')
  }
} catch (err) {
  console.error('更新 config.json 失败：' + (err?.message || err))
}
