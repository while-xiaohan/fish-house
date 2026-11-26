// 大肥鱼的小屋 · 鲸鲸桥接插件
//
// 作用：鲸鲸收到/发出微信消息时，通知本机小屋服务切换视频状态（拿手机 → 回消息 → 放手机）。
//       另外，消息里出现「换睡衣 / 睡衣 / 睡觉」就切睡衣模式；出现「起床 / 换衣服 / 上班」切回日常。
// 服务地址默认 http://127.0.0.1:8899，由 dsh-fish-house 插件拉起。
//
// 失败一律静默：小屋没开不能影响鲸鲸正常回消息。

const http = require('node:http');

const HOST = '127.0.0.1';
const PORT = 8899;
const TIMEOUT_MS = 500;

// 不再写死某个主题的节点 id：只发语义动作，由小屋按当前主题画布解析节点。
// 这样换成「小肥鱼的零食」这类没有旧睡衣节点的主题时，不会去切一个不存在的节点。

const PAJAMA_WORDS = ['换睡衣', '睡衣', '睡觉', '去睡', '躺下睡'];
const DAY_WORDS = ['起床', '换衣服', '穿上衣服', '睡醒了'];  // 别用「上班/干活」这类泛词，聊天里随便一提就把睡衣态切走了

let lastAt = 0;

function post(payload) {
  try {
    const body = Buffer.from(JSON.stringify(payload));
    const req = http.request({
      host: HOST,
      port: PORT,
      path: '/hook',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': body.length,
      },
      timeout: TIMEOUT_MS,
    }, (res) => res.resume());
    req.on('error', () => {});
    req.on('timeout', () => req.destroy());
    req.write(body);
    req.end();
  } catch {
    // 忽略
  }
}

function notify(action, extra, force = false) {
  const now = Date.now();
  // 连发多条消息时没必要每条都打一次；睡衣/起床口令要单独放行，避免把 reply 挤掉
  if (!force && now - lastAt < 300) return;
  lastAt = now;
  post({ action, ...(extra || {}) });
}

module.exports = {
  hooks: {
    // 收到消息：鱼伸手拿手机；顺便识别「换睡衣 / 起床」这类口令
    async 'chat.received'(input) {
      const message = (input && input.message) || {};
      const text = String(message.text || '');
      if (PAJAMA_WORDS.some((word) => text.includes(word))) {
        notify('pajama', {}, true);
      } else if (DAY_WORDS.some((word) => text.includes(word))) {
        notify('day', {}, true);
      }
      const who = String(message.senderName || message.chatTitle || '').slice(0, 20);
      notify('reply', who ? { text: who } : {});
      return {};  // 这些钩子不接受 action=pass，返回空对象才不会被判成 plugin_error
    },
    // 回复已发出：保持手机态（小屋自己会在超时后放手机）
    async 'chat.dispatched'() {
      notify('reply');
      return {};  // 这些钩子不接受 action=pass，返回空对象才不会被判成 plugin_error
    },
  },
};
