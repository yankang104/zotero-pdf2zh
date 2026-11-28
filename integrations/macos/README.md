# macOS 自动启停与 Finder 右键翻译

本目录把 macOS 的自动监控、Quick Action、系统通知和 Finder 定位接到项目唯一的主后端 `server/server.py`，不再提供独立翻译服务器。需要完整项目目录；仅安装 XPI 或解压 `server.zip` 不包含本集成。

- 自动监控每 10 秒检查 Zotero：打开时启动服务，关闭且没有活动翻译任务时停止服务。
- Finder 选中一个 PDF 后，可通过快速操作提交翻译，完成时通知并在 Finder 中选中结果。
- 监控、手动启动和客户端自动启动共用 `start_server.sh`、端口 **8888**、`logs/zotero_python.pid` 和 `logs/server.log`。
- 重复执行 `start` 会复用已运行的进程；只有显式 `restart` 才会先停止它。

## 1. 目录与前提

```text
zotero-pdf2zh/
├── server/
│   ├── server.py
│   ├── pdf2zh_server/
│   └── config/config.json
├── integrations/macos/
│   ├── README.md
│   ├── start_server.sh
│   ├── zotero_monitor.sh
│   ├── translate_pdf_client.py
│   ├── translate_pdf_quick_action.sh
│   ├── com.user.zotero.monitor.plist
│   └── config.json                 # 可选的本地翻译配置，不纳入版本控制
└── logs/                           # 运行时日志和 PID
```

先按[项目主说明](../../README.md)准备主 Server 和 `pdf2zh_next` 翻译环境，并确认能正常完成一篇翻译。本集成保留原有 Conda 启动参数：`--enable_venv True --env_tool conda --skip_install True`，不会代替首次环境安装。后台启动额外关闭源码更新交互，避免在无人值守时等待输入。

脚本默认 Python 为 `/opt/anaconda3/envs/zotero-pdf2zh-next-venv/bin/python`。如果使用其他安装位置，设置 `ZOTERO_PDF2ZH_PYTHON` 为实际 Python 的绝对路径；LaunchAgent 也需要设置同一个变量，并在其 `PATH` 中包含实际 Conda 的 `bin` 目录。Python 客户端只使用标准库和仓库内的服务商字段映射，但启动的主 Server 仍需其正常依赖。

在 macOS 终端进入项目根目录，为现有脚本设置执行权限：

```bash
cd /Users/你的用户名/Documents/zotero-pdf2zh
chmod +x integrations/macos/*.sh
```

`terminal-notifier` 是可选通知工具；找不到时使用 macOS 自带的 `osascript`。是否显示通知取决于本机通知设置。

## 2. 翻译配置

Finder 客户端按顺序读取：

1. `integrations/macos/config.json`，存在时使用其中内容。
2. 否则使用主 Server 的 `server/config/config.json`。

客户端使用 `translators` 数组的**第一项**作为当前服务商，从 JSON 配置中读取 API Key、URL、模型及适用于该服务商的附加参数，将请求发送给 `pdf2zh_next`。已有的 `openailiked` 服务会映射到 Next 的 `openaicompatible`。客户端不会改写 JSON 配置文件，也不会直接读取 Zotero 插件的偏好设置或 Next 的 TOML 配置。

例如，本地 `integrations/macos/config.json` 可以使用以下格式：

```json
{
  "translators": [
    {
      "name": "openailiked",
      "envs": {
        "OPENAILIKED_API_KEY": "你的 API Key",
        "OPENAILIKED_BASE_URL": "你的服务商 API 地址",
        "OPENAILIKED_MODEL": "你的模型名称"
      }
    }
  ]
}
```

旧的 `automation/` 或 `macos/` 目录里若有自有 `config.json`，请保留原内容并迁至 `integrations/macos/config.json`；原本使用 `server/config/config.json` 的用户可以继续使用原位置。升级前先用旧脚本停止旧服务、卸载旧 LaunchAgent，再替换路径。旧的 `server_direct.pid` 不会被当作新的受管进程；旧服务应通过其原启动方式停止。

Finder 入口使用 `pdf2zh_next`、4 个请求/秒、英语译为中文，取主 Server 返回的双语 PDF，另存为原文件旁的 `<原名>-dual.pdf`。同名结果会覆盖。Server 中生成的其他产物仍留在其输出目录，客户端不会把它们全部复制回原目录。

## 3. 手动启动、停止和查看状态

从项目根目录运行：

```bash
bash integrations/macos/start_server.sh start
bash integrations/macos/start_server.sh status
bash integrations/macos/start_server.sh restart
bash integrations/macos/start_server.sh stop
```

自定义 Python 的示例：

```bash
export ZOTERO_PDF2ZH_PYTHON="$HOME/miniconda3/envs/zotero-pdf2zh-next-venv/bin/python"
bash integrations/macos/start_server.sh start
```

`status` 显示这套脚本管理的进程状态，服务能否接收请求可查看 `http://127.0.0.1:8888/health`。若主 Server 已由其他终端启动在 8888，客户端可以直接复用；管理脚本不会接管该进程。Zotero 插件若也使用这项服务，需将其 Server 地址设置为 `http://127.0.0.1:8888`。

## 4. 自动监控

编辑 `com.user.zotero.monitor.plist`，把脚本与两处日志路径中的 `/Users/你的用户名/Documents/zotero-pdf2zh` 全部换成实际项目路径。脚本内部会按自身位置找到项目根目录，通常不需要再次硬编码路径。

使用自定义 Python 时，在 plist 的 `EnvironmentVariables` 字典加入：

```xml
<key>ZOTERO_PDF2ZH_PYTHON</key>
<string>/实际路径/envs/zotero-pdf2zh-next-venv/bin/python</string>
```

然后在 macOS 终端安装监控配置：

```bash
mkdir -p "$HOME/Library/LaunchAgents" logs
cp integrations/macos/com.user.zotero.monitor.plist "$HOME/Library/LaunchAgents/"
launchctl load "$HOME/Library/LaunchAgents/com.user.zotero.monitor.plist"
```

修改已安装的 plist 后，先 `launchctl unload` 再 `launchctl load` 同一个文件。打开 Zotero 后，监控会启动主 Server；关闭 Zotero 后，会等待 Finder 客户端退出及 `/api/tasks` 中的活动任务完成再停止，避免中断客户端启动、翻译或结果下载。任务接口暂不可用时保留进程，等下一轮检查。

自动监控启用且 Zotero 仍打开时，手动 `stop` 后会在下一轮重新启动。需要持续停用时，应先卸载监控，再停止服务：

```bash
launchctl unload "$HOME/Library/LaunchAgents/com.user.zotero.monitor.plist"
bash integrations/macos/start_server.sh stop
```

## 5. Finder Quick Action

先确认能从终端提交一个真实 PDF：

```bash
"$ZOTERO_PDF2ZH_PYTHON" integrations/macos/translate_pdf_client.py "/实际路径/论文.pdf"
```

如果没有设置 `ZOTERO_PDF2ZH_PYTHON`，用准备好主 Server 依赖的 Python 路径代替上面的变量。客户端会复用已运行的 8888 服务；没有运行时，通过同一个管理脚本启动并等待 `/health` 就绪。

在 Automator 新建“快速操作”，将输入设为 Finder 中的 PDF 文件，加入“运行 Shell 脚本”，Shell 选择 `/bin/bash`，传递输入选择“作为自变量”。内容为：

```bash
#!/bin/bash
exec /bin/bash "/Users/你的用户名/Documents/zotero-pdf2zh/integrations/macos/translate_pdf_quick_action.sh" "$@"
```

将绝对路径换为实际项目位置，保存为“翻译 PDF 文档”。当前入口每次处理一个 PDF；在 Finder 中选中一个文件，右键选择相应快速操作。按系统提示授予实际需要的访问和通知权限。

客户端通过 `/translate` 提交任务，收到 `accepted` 后查询 `/api/tasks` 和 `/api/history`，按 `fileList` 返回的真实文件名下载结果。翻译过程中在达到 25%、50%、75%、90% 时通知，成功后通知并在 Finder 中定位双语 PDF。

## 6. 日志、移除与验收限制

- 主 Server：项目根目录 `logs/server.log`。
- 自动监控：`logs/monitor.log` 和 plist 指定的 `logs/launchagent_*.log`。
- Finder 包装脚本：`~/Library/Logs/PDFTranslateQuickAction.log`。

找不到 Python 时，核对实际解释器路径和 LaunchAgent 的环境变量；启动失败时先查看 `server.log`。API 或模型错误会保留主 Server 返回的错误信息，不需要再启动旧的独立服务器。

移除本集成时，先卸载 LaunchAgent 并停止受管 Server，再删除 `~/Library/LaunchAgents/com.user.zotero.monitor.plist` 和 `~/Library/Services/` 中对应的 Quick Action。保留主项目、用户 API 配置和翻译文件即可。

离线测试命令：

```bash
python -m unittest discover -s integrations/macos/tests -p "test_*.py"
```

测试使用模拟 HTTP 与系统调用，覆盖 JSON 配置转换为 Next 请求、主 Server 启动衔接、accepted 任务轮询、错误传递和返回文件下载。Shell 脚本另做 Bash 语法检查。这些检查不能证明 macOS 的 LaunchAgent、Automator、通知权限和 Finder 交互正常；上述部分仍需在真实 macOS 上验收。本次维护环境为 Windows，未运行 macOS 启停命令、未安装 LaunchAgent、未修改本机运行配置。
