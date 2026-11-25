// dsh-fish-house —— 把「大肥鱼的小屋」从 AstrBot 搬到 DeepSeek Harness。
//
// 组成：
//   runner/serve.py    原版 fish-house v2.0.1 逻辑 + astrbot 兼容壳（独立进程，端口默认 8899）
//   本文件             cordis 插件：拉起 runner、把 DSH 回合状态翻译成小屋动作
//
// 事件映射：
//   turn/start      → work_start（拿手机 → 走到电脑 → 电脑循环）
//   step/tool 事件  → 记「还在干活」，工具名顺带当气泡
//   turn/end        → 只有在回合/步骤/工具/子 agent 全空了才算真干完，才发 work_end

import { spawn } from 'node:child_process'
import { existsSync } from 'node:fs'
import { appendFile, mkdir, readFile } from 'node:fs/promises'
import { homedir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

export const name = 'dsh-fish-house'

const HERE = dirname(fileURLToPath(import.meta.url))
const PKG = dirname(HERE)

const API = '/api/v1/plugins/extensions/astrbot_plugin_fish_house'

const DEFAULTS = {
  host: '127.0.0.1',
  port: 8899,
  python: '',
  source: '',
  autoStart: true,
  toolBubble: true,
  finishGraceMs: 2500,
}

function dshHome() {
  return process.env.DSH_HOME || join(homedir(), '.dsh')
}

function stateDir() {
  return join(dshHome(), 'dsh-fish-house')
}

function logPath() {
  return join(stateDir(), 'runner.log')
}

async function log(line) {
  try {
    await mkdir(stateDir(), { recursive: true })
    await appendFile(logPath(), `[${new Date().toISOString()}] ${line}\n`)
  } catch {
    /* 日志失败不影响主流程 */
  }
}

/** 找 python：先看配置，再试本机常见位置，最后落到 PATH 里的 python。 */
function resolvePython(configured) {
  if (configured && existsSync(configured)) return configured
  const candidates = [
    'E:\\AI\\DeepSeek\\.venv\\Scripts\\python.exe',
    'E:\\AI\\WhaleGirl\\runtime\\python.exe',
    join(homedir(), 'AppData', 'Local', 'Programs', 'Python', 'Python313', 'python.exe'),
  ]
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate
  }
  return 'python'
}

export function apply(ctx, config = {}) {
  const cfg = { ...DEFAULTS, ...config }
  const base = `http://${cfg.host}:${cfg.port}`
  const source = cfg.source && existsSync(cfg.source) ? cfg.source : join(PKG, 'upstream-v2.0.1')
  const dataDir = join(PKG, 'data')

  const state = {
    child: null,
    ready: false,
    stopping: false,
    lastAction: '',
    lastActionAt: 0,
    petWork: false,
    finishTimer: null,
    toolSeq: 0,
  }

  async function isHealthy() {
    try {
      const res = await fetch(`${base}/health`, { signal: AbortSignal.timeout(2000) })
      return res.ok
    } catch {
      return false
    }
  }

  async function waitHealthy(timeoutMs = 45000) {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      if (await isHealthy()) return true
      await new Promise((r) => setTimeout(r, 700))
    }
    return false
  }

  function launch() {
    if (state.child || state.stopping) return
    const python = resolvePython(cfg.python)
    const args = [join(PKG, 'runner', 'serve.py'), '--host', cfg.host, '--port', String(cfg.port)]
    log(`启动 runner：${python} ${args.join(' ')}`)
    const child = spawn(python, args, {
      cwd: PKG,
      windowsHide: true,
      env: {
        ...process.env,
        FISH_HOUSE_SRC: source,
        FISH_HOUSE_DATA: dataDir,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUTF8: '1',
      },
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    state.child = child
    child.stdout.on('data', (buf) => log(`[out] ${String(buf).trimEnd()}`))
    child.stderr.on('data', (buf) => log(`[err] ${String(buf).trimEnd()}`))
    child.on('exit', (code, signal) => {
      log(`runner 退出：code=${code} signal=${signal}`)
      state.child = null
      state.ready = false
      if (!state.stopping) {
        // 内核被手动杀掉时给一次自动重拉；连续崩就不无限重试
        setTimeout(() => {
          if (!state.stopping && !state.child) {
            launch()
            waitHealthy().then((ok) => { state.ready = ok })
          }
        }, 3000)
      }
    })
  }

  async function ensureReady() {
    if (state.ready && (await isHealthy())) return true
    if (!state.child) launch()
    state.ready = await waitHealthy()
    if (state.ready) await log('runner 已就绪')
    else await log('runner 启动失败（可看 runner.log）')
    return state.ready
  }

  async function post(payload) {
    if (!(await ensureReady())) return
    const key = JSON.stringify(payload)
    const now = Date.now()
    // 同一动作 400ms 内不重复发，避免多会话一起刷
    if (key === state.lastAction && now - state.lastActionAt < 400) return
    state.lastAction = key
    state.lastActionAt = now
    try {
      const res = await fetch(`${base}${API}/event`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: key,
        signal: AbortSignal.timeout(8000),
      })
      if (!res.ok) await log(`event ${res.status}：${key}`)
      else if (payload.action !== 'work_ping') await log(`${payload.action} ok（${payload.activity || '无气泡'}）`)
    } catch (err) {
      await log(`event 失败：${err?.message || err}`)
    }
  }

  // 「还在干活」= 有回合没结束、有模型步骤没结束、有工具没返回、有子 agent 在忙。
  // 屋里只有这四样全空了才算真干完，那时才让它回窝，不做任何“等几秒就睡”的猜测。
  const busy = {
    turns: new Map(),
    steps: new Map(),
    tools: new Map(),
    agents: new Map(),
  }

  function pruneMap(map, maxAgeMs) {
    const now = Date.now()
    for (const [key, at] of map) {
      if (now - at > maxAgeMs) map.delete(key)
    }
  }

  function busyCount() {
    pruneMap(busy.turns, 6 * 60 * 60 * 1000)
    pruneMap(busy.steps, 30 * 60 * 1000)
    pruneMap(busy.tools, 30 * 60 * 1000)
    pruneMap(busy.agents, 30 * 60 * 1000)
    return busy.turns.size + busy.steps.size + busy.tools.size + busy.agents.size
  }

  function clearFinish() {
    if (state.finishTimer) {
      clearTimeout(state.finishTimer)
      state.finishTimer = null
    }
  }

  function markWork(activity) {
    clearFinish()
    if (state.petWork) return
    state.petWork = true
    post({ action: 'work_start', activity: activity || '在电脑前干活' })
  }

  function markIdle() {
    if (!state.petWork || state.finishTimer) return
    state.finishTimer = setTimeout(() => {
      state.finishTimer = null
      if (busyCount() > 0) return
      state.petWork = false
      post({ action: 'work_end' })
    }, Math.max(300, Number(cfg.finishGraceMs) || 2500))
  }

  function syncWork() {
    if (busyCount() > 0) markWork()
    else markIdle()
  }

  function onSessionEvent(session, event) {
    try {
      const type = String(event?.type || '')
      const data = event?.data || {}
      const sid = String(session?.id || 'unknown')
      if (type === 'turn/start') {
        busy.turns.set(sid, Date.now())
        const title = String(session?.title || '').trim().slice(0, 24)
        markWork(title || '在电脑前干活')
        return
      }
      if (type === 'turn/end') {
        busy.turns.delete(sid)
        syncWork()
        return
      }
      if (type === 'step/start') {
        busy.steps.set(`${sid}:${data.turn ?? ''}:${data.step ?? ''}`, Date.now())
        syncWork()
        return
      }
      if (type === 'step/end') {
        busy.steps.delete(`${sid}:${data.turn ?? ''}:${data.step ?? ''}`)
        syncWork()
        return
      }
      if (type === 'tool/call') {
        const callId = String(data.callId || data.call_id || data.id || `${sid}:${++state.toolSeq}`)
        busy.tools.set(callId, Date.now())
        const tool = String(data.name || '').slice(0, 40)
        if (cfg.toolBubble && tool) post({ action: 'work_ping', activity: `工具：${tool}` })
        markWork()
        return
      }
      if (type === 'tool/result') {
        const callId = String(data.callId || data.call_id || data.id || '')
        if (callId) busy.tools.delete(callId)
        else {
          const oldest = busy.tools.keys().next()
          if (!oldest.done) busy.tools.delete(oldest.value)
        }
        syncWork()
        return
      }
      if (type === 'agent/status') {
        const id = String(data.agent?.id || data.agent || sid)
        const status = String(data.status || '')
        if (/busy|running|working|thinking|streaming/i.test(status)) busy.agents.set(id, Date.now())
        else busy.agents.delete(id)
        syncWork()
        return
      }
      if (type === 'assistant/message') {
        if (busyCount() > 0) post({ action: 'work_ping' })
      }
    } catch (err) {
      log(`session/event 处理失败：${err?.message || err}`)
    }
  }

  ctx.on('session/event', onSessionEvent)

  // 还标着“干活”时定期续期：模型长思考、工具长执行期间没有新事件，
  // 靠心跳顶住小屋的闲置倒计时，避免活儿没干完就被兜底逻辑赶回窝。
  const heartbeat = setInterval(() => {
    if (state.petWork && busyCount() > 0) post({ action: 'work_ping' })
  }, 20000)

  if (cfg.autoStart) {
    ensureReady().catch((err) => log(`启动异常：${err?.message || err}`))
  }

  ctx.effect(() => () => {
    state.stopping = true
    clearInterval(heartbeat)
    if (state.finishTimer) clearTimeout(state.finishTimer)
    if (state.child) {
      try {
        state.child.kill()
      } catch {
        /* ignore */
      }
      state.child = null
    }
    return Promise.resolve()
  })
}

export default { name, apply }
