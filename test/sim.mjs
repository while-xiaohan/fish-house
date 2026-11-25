// 开发自测：用假 ctx 驱动插件，验证事件 → 状态机映射
import { apply } from '../lib/index.js'

const listeners = new Map()
const ctx = {
  on(name, fn) { listeners.set(name, fn) },
  effect(fn) { this._dispose = fn() },
}

const plugin = apply(ctx, { port: 8901, autoStart: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const health = async () => {
  try {
    const res = await fetch('http://127.0.0.1:8901/api/v1/plugins/extensions/astrbot_plugin_fish_house/state')
    return await res.json()
  } catch (e) { return { error: String(e) } }
}

await sleep(9000)
console.log('初始:', (await health()).state?.mode)

const fire = (type, data = {}) => listeners.get('session/event')?.({ id: 's1', title: '测试会话' }, { type, data })

fire('turn/start')
await sleep(1500)
console.log('回合开始:', (await health()).state?.mode)

fire('tool/call', { name: 'edit' })
await sleep(800)
console.log('工具调用:', (await health()).state?.event, (await health()).state?.bubble)

fire('turn/end')
await sleep(3000)
console.log('回合结束:', (await health()).state?.mode)

process.exit(0)
