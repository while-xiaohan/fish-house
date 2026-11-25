# dsh-fish-house · 大肥鱼的小屋（DSH 版）

把原本跑在 **AstrBot** 上的 [`astrbot_plugin_fish_house`](https://github.com/jiuchai/fish-house)（v2.0.1）
搬到 **DeepSeek Harness（DSH）** 上运行，并和 DSH 的回合状态、鲸鲸的微信消息联动。

原版 3383 行逻辑（状态机、面板、主题/项目、主题市场、上传、备份）**一行没改**，
外面套了一层 `astrbot` 兼容壳（`runner/astrbot/`），所以 AstrBot 主程序完全不需要安装或启动。

## 组成

```
dsh-fish-house/
├── lib/index.js        DSH（cordis）插件：拉起 runner + 把 DSH 回合事件翻译成小屋动作
├── runner/serve.py     独立 HTTP 服务（面板 / 公共壁纸页 / 原版 17 个接口 / hook）
├── runner/astrbot/     astrbot.api 兼容壳（logger / web / star / event / provider / 配置 / 路径）
├── upstream-v2.0.1/    原版 fish-house v2.0.1 源码（只作为源码引用，不修改）
├── whale-plugin/       鲸鲸桥接插件源码（生成 data/plugins 下的 flow.json）
├── tools/              安装脚本
└── data/               运行数据（视频、主题、配置、备份、公共页）
```

## 地址

| 用途 | 地址 |
|---|---|
| 管理面板（主题 / 项目 / 市场 / 素材 / 设置） | <http://127.0.0.1:8899/panel/> |
| 公共壁纸页（放 OBS / 当桌面壁纸） | <http://127.0.0.1:8899/fish_house/index.html> |
| 健康检查 | <http://127.0.0.1:8899/health> |
| 状态驱动口（给别的程序用） | `POST http://127.0.0.1:8899/hook` |

## 状态怎么被驱动

| 来源 | 事件 | 小屋动作 |
|---|---|---|
| DSH | `turn/start` | `work_start`：拿手机 → 走到电脑 → 电脑循环 |
| DSH | `tool/call` | `work_ping`：续期，气泡显示「工具：xxx」 |
| DSH | `assistant/message` | `work_ping`：保持干活 |
| DSH | `turn/end` | `work_end`：延迟 1.5 秒回休息（连续回合不来回切） |
| 鲸鲸 | `chat.received` | `reply`：伸手拿手机 |
| 鲸鲸 | `chat.dispatched` | `reply`：保持手机态，超时自动放下 |

`/hook` 的 payload 与面板 `/event` 接口一致，支持的 action：
`reply` / `work_start` / `work_ping` / `work_end` / `rest` / `bubble` / `play_action` / `flow_goto`。

## 安装 / 卸载

```powershell
node tools\install-dsh.mjs        # 装进 ~/.dsh/profiles/desktop（建 junction + 登记 bundle）
node tools\install-whale.mjs      # 装进鲸鲸 data/plugins 并打开 features.javascriptPlugins
node tools\install-dsh.mjs --uninstall
node tools\install-whale.mjs --uninstall
```

装完重启 DeepSeek Harness 才会加载插件。

## 配置

`cordis.patch.yml` 里改：

```yaml
- insert:
    - id: dsh-fish-house
      config:
        host: 127.0.0.1
        port: 8899
        python: ''      # 留空自动找 venv / PATH 里的 python
        source: ''      # 留空用包内 upstream-v2.0.1
        autoStart: true
        toolBubble: true
        endGraceMs: 1500
```

## 与 dsh-pet（鲸鱼娘桌宠）的关系

两边听的是同一套 DSH 回合事件：DSH 一干活，桌宠进入工作动作，小屋视频切到「去电脑 / 电脑循环」；
回合结束，两边一起回休息。不需要额外的同步通道。

## 已知边界

- 只在 Windows 本机验证；依赖 `python`（stdlib 即可，无需 pip 安装任何包）。
- 面板里的「独立公共链接」用的是本机地址，没有做反向代理/HTTPS。
- 主题市场仍然走外部 `shop.swellengine.com`，登录/上传需要联网。
