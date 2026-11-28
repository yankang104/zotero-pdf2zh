# 项目架构与维护入口

本项目按业务功能组织。Zotero 插件负责交互、任务提交和附件导入；Server 负责任务编排、引擎执行和产物发布。PDFMathTranslate、PDFMathTranslate-next、BabelDOC 和 Wenyi 仍是各自独立安装的上游程序。

## 目录与职责

| 位置 | 内容 |
| --- | --- |
| `plugin/src/settings/` | API 配置唯一状态、偏好持久化、翻译配置、设置页和配置表格 |
| `plugin/src/translation/` | 任务工作流、Server 通信、能力协商、进度和输出模式 |
| `plugin/src/attachments/` | PDF 读取、结果筛选与导入、附件标题 |
| `plugin/src/menus/` | 原生菜单注册及多窗口兼容 |
| `plugin/src/utils/` | 通用 Zotero 偏好、语言、窗口和 toolkit 工具 |
| `plugin/addon/content/settings/` | 原生设置页和配置编辑器；页面结构与脚本、样式分别维护 |
| `server/pdf2zh_server/configuration/` | 请求字段解析、配置文件写入、任务快照和已有配置补全 |
| `server/pdf2zh_server/tasks/` | 任务服务、状态、取消、进度和独立任务工作区 |
| `server/pdf2zh_server/providers/` | 内置服务映射、自定义服务路由、模型目录、请求头、请求体和协议适配 |
| `server/pdf2zh_server/engines/` | Next、Wenyi 的执行入口及子进程、终端处理 |
| `server/pdf2zh_server/pdf/` | PDF 产物命名、裁剪对比、参考文献和表格处理 |
| `server/pdf2zh_server/environment/` | 环境定位、版本能力读取、安装更新、提示和包源 |
| `server/pdf2zh_server/web/` | 监控页面及其脚本、样式和运行资源 |
| `deployment/docker/` | `engine-container` 与 `engine-image` 两种部署方式 |
| `integrations/macos/` | 使用主 Server 的右键翻译、监控、启动与通知 |
| `docs/zh/`、`docs/en/` | 用户文档 |
| `docs/development/` | 开发架构、协议和各功能的技术说明 |

源码、原生资源和测试分别保留各自的构建边界，但使用相同业务名称。插件测试按 settings、translation、attachments、menus 等分组；Server 测试按后端功能分组。

## 插件调用与数据所有权

```text
hooks → 菜单 / 设置页注册 / 翻译工作流
翻译工作流 → 配置数据 + PDF 读取 + Server 通信 + 结果导入 + 进度界面
结果导入 → 下载 + PDF 文件处理 + 标题规则
设置页 → 配置数据 + 本地表格控制器 + 原生编辑窗口
```

- `settings/apiConfigurations.ts` 是 API 配置唯一内存状态。`reloadApiConfigurations()` 从现有偏好数组加载；保存成功后更新该状态，失败沿用已有回滚规则。
- `settings/translationConfig.ts` 提供 `getTranslationConfig(mode?)`。翻译在提交前重新加载 API 配置，读取激活条目，无需打开设置页。
- `settings/apiTable.ts` 只保存该页面的行键、选择和控件状态；配置对象不再复制到 `addon.data` 的另一份 Map。
- `translation/workflow.ts` 编排批量和单文件任务。`serverClient.ts` 只处理通信，通过进度与通知回调交给界面显示。
- 配置编辑器依次加载预设、参数、请求头、请求体、模型和控制器。模块通过初始化参数和回调连接；模型目录继续使用显式注入的 Zotero HTTP 直接访问服务商。
- 持久化偏好键、API JSON 形状、编辑器历史键、菜单 ID 和主后端请求协议保持原有约定。

## Server 调用与运行边界

```text
server.py → startup → ServerApplication
                       ├→ ServerApi → TranslationService
                       └→ 环境管理器、任务管理器、引擎与 PDF 处理对象
TranslationService → 请求配置 / 工作区 / 引擎执行 / 任务状态
引擎执行 → 子进程输出 → 进度回调 → 所属应用的任务管理器
```

`server.py` 保留 `__version__` 字面量和原启动命令。`application.py` 组装具体依赖；`api.py` 负责 HTTP 请求、响应、状态码和 SSE；`tasks/service.py` 不依赖 Flask。

配置字段沿用现有 `Config`，文件写入和凭据清理位于 `configuration/storage.py`。任务使用独立输入、配置快照与输出目录；引擎返回产物路径，由任务工作区统一发布。

Next 的适配入口位于 `engines/next_runtime/`，通过明确的绝对脚本路径启动。Wenyi 的 runner、bridge 保持独立 Python 和 `-I` 隔离方式。协议、表格与参考文献适配仍在引擎子进程中安装，不把上游引擎包提前导入 HTTP 进程。

`paths.py` 以安装包的 `server/` 为根定位配置和输出。源码移动不改变 `server/config/`、`server/translated/`、任务工作区、现有虚拟环境或 Wenyi 用户数据的默认位置。首页、favicon、提示音及现有 HTTP/SSE 路径保持原有约定。

## 构建、发布与维护

```shell
cd plugin
npm test
npm run lint:check
npm run build
cd ..
python -m unittest discover -s server/tests -p "test_*.py"
python -m unittest discover -s integrations/macos/tests -p "test_*.py"
python pack_server.py
```

Server 测试需在具有 `server/requirements.txt` 依赖的环境运行，并将 `server` 加入 `PYTHONPATH`；可直接使用项目已有测试环境。真实引擎相关用例沿用各自的启用条件，不在测试中自动安装或更新用户引擎。

两个安装包固定为根目录 `zotero-pdf-2-zh.xpi` 和 `server.zip`。插件构建后移动 XPI；Server 打包只收集程序目录、命令入口、示例配置和必要资源。标签触发的发布流程使用同一打包脚本，将安装包与对应清单上传到版本 Release，再把该次 Release 的清单更新到 `zotero-updates` 分支。Zotero 从这个分支读取更新清单，从版本 Release 下载 XPI。

旧快照和嵌套源码副本不参与当前维护，历史由 Git 保留。升级安装只更新程序文件，沿用既有用户数据保留规则，不增加运行时递归清理程序。

后续改动优先进入对应现有功能模块。只有职责独立、确有长期维护价值时才新增文件；通用目录中不放置完整业务流程。技术说明直接更新相应功能文档，不另留同主题临时总结。

真实 Zotero 窗口、macOS 通知与 Finder、Docker 容器以及在线翻译分别需要对应运行环境。单元测试、构建和静态检查的通过，不代替这些实机验收。
