;(() => {
  // 大肥鱼的小屋 · DSH 客户端半侧
  //
  // 两个入口：
  //  1) DSH 右侧栏（用户口中的「任务栏」）的「大肥鱼的小屋」标签页；
  //  2) 设置 →「大肥鱼的小屋」分区。
  //
  // 面板用 iframe 直嵌。实测 DSH 页面本身没有 CSP，8899 也不发
  // X-Frame-Options，iframe 能正常显示；webview 在桌面版里没有 attach，
  // 会是一片黑，所以这里不用 webview。
  const PANEL_URL = "http://127.0.0.1:8899/panel/";

  function makeFactory() {
    return (require) => {
      const React = require("react");
      const h = React.createElement;
      const name = "fish-house-panel";
      const inject = ["slots", "sidebarRight", "betterSidebar"];
      const TAB_KIND = "dsh-fish-house:panel";

      let ctxRef = null;

      function rightSidebar() {
        return ctxRef && ctxRef.sidebarRight;
      }

      function openCustomTab() {
        const right = rightSidebar();
        if (!right || typeof right.openTab !== "function") return false;
        try {
          right.openTab(TAB_KIND, { params: {} });
          return true;
        } catch (err) {
          return false;
        }
      }

      function openBrowserTab() {
        const right = rightSidebar();
        if (right && typeof right.openTab === "function") {
          try {
            right.openTab("browser", { params: { url: PANEL_URL } });
            return true;
          } catch (err) {
            console.warn("[dsh-fish-house] 右侧栏 Browser 打不开：", err);
          }
        }
        return false;
      }

      function openExternal() {
        window.open(PANEL_URL, "_blank", "noopener");
      }

      const buttonStyle = {
        fontSize: 12,
        padding: "3px 9px",
        borderRadius: 6,
        border: "1px solid rgba(128,128,128,.35)",
        background: "transparent",
        color: "inherit",
        cursor: "pointer",
        flex: "none",
      };

      // —— iframe 面板：右侧栏标签页和设置分区共用 ——
      function Panel(props) {
        const height = (props && props.height) || "100%";
        const [frameKey, setFrameKey] = React.useState(0);

        return h(
          "div",
          {
            style: {
              display: "flex",
              flexDirection: "column",
              height,
              minHeight: 360,
              background: "#111",
              overflow: "hidden",
            },
          },
          h(
            "div",
            {
              style: {
                display: "flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 10px",
                borderBottom: "1px solid rgba(128,128,128,.25)",
                flex: "none",
                color: "#ddd",
              },
            },
            h(
              "span",
              {
                style: {
                  fontSize: 12,
                  opacity: 0.75,
                  flex: 1,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                },
              },
              PANEL_URL
            ),
            h(
              "button",
              {
                type: "button",
                title: "重新加载面板",
                style: buttonStyle,
                onClick: () => setFrameKey((k) => k + 1),
              },
              "刷新"
            ),
            h(
              "button",
              {
                type: "button",
                title: "在右侧栏 Browser 标签打开",
                style: buttonStyle,
                onClick: openBrowserTab,
              },
              "Browser 打开"
            ),
            h(
              "button",
              {
                type: "button",
                title: "用系统浏览器打开",
                style: buttonStyle,
                onClick: openExternal,
              },
              "浏览器打开"
            )
          ),
          h("iframe", {
            key: frameKey,
            src: PANEL_URL,
            title: "大肥鱼的小屋管理面板",
            allow: "autoplay; clipboard-read; clipboard-write",
            style: {
              border: 0,
              flex: 1,
              width: "100%",
              minHeight: 320,
              display: "block",
              background: "#111",
            },
          })
        );
      }

      function TabPanel() {
        return h(Panel, { height: "100%" });
      }

      function SettingsPanel() {
        return h(Panel, { height: 560 });
      }

      function apply(ctx) {
        ctxRef = ctx;

        // 1) 设置页分区
        ctx.slots.inject("settings.section", () =>
          ctx.slots.register(
            {
              name: "settings.section",
              id: "fish-house-panel",
              order: 31,
              label: () => "大肥鱼的小屋",
            },
            SettingsPanel
          )
        );

        // 2) 右侧栏标签页。注册类型后主动打开一次，让它出现在右侧那一列。
        ctx.effect(() => {
          let dispose = null;
          try {
            dispose = ctx.betterSidebar.registerTab({
              id: TAB_KIND,
              title: "大肥鱼的小屋",
              description: "鱼屋面板：主题、动作与视频状态机管理",
              icon: (size) =>
                h(
                  "svg",
                  {
                    viewBox: "0 0 24 24",
                    width: size || 16,
                    height: size || 16,
                    fill: "none",
                    "aria-hidden": true,
                  },
                  h("path", {
                    d: "M3 11.2 12 4.4l9 6.8",
                    stroke: "currentColor",
                    strokeWidth: 1.8,
                    strokeLinecap: "round",
                    strokeLinejoin: "round",
                  }),
                  h("path", {
                    d: "M5.4 11v7.2h13.2V11",
                    stroke: "currentColor",
                    strokeWidth: 1.8,
                    strokeLinecap: "round",
                  }),
                  h("path", {
                    d: "M9.2 15.1c1-1.5 4.6-1.7 6-.3-1.4 1.4-5 1.2-6 .3Z",
                    fill: "currentColor",
                    opacity: 0.9,
                  })
                ),
              single: true,
              component: () => h(TabPanel, {}),
            });
          } catch (err) {
            // HMR 重载时旧注册可能还没释放；类型已存在就直接复用。
            console.warn("[dsh-fish-house] 注册侧边栏标签失败：", err);
          }

          let retryTimer = null;
          let tries = 0;
          const startTimer = setTimeout(() => {
            let already = false;
            try {
              already = sessionStorage.getItem("fish-house-tab-opened") === "1";
            } catch {
              /* sessionStorage 不可用时每次都打开 */
            }
            if (already) return;

            const attempt = () => {
              if (openCustomTab()) {
                try {
                  sessionStorage.setItem("fish-house-tab-opened", "1");
                } catch {
                  /* ignore */
                }
                return;
              }
              if (++tries < 40) retryTimer = setTimeout(attempt, 500);
            };
            attempt();
          }, 800);

          return () => {
            clearTimeout(startTimer);
            if (retryTimer) clearTimeout(retryTimer);
            if (typeof dispose === "function") dispose();
          };
        }, "dsh-fish-house: right sidebar tab");
      }

      return { apply, inject, name };
    };
  }

  window.__ModuleLoader__.load({
    id: "dsh-fish-house",
    factory: makeFactory(),
  });
})();
