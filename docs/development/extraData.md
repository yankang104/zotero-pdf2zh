插件 LLM 配置的基础字段为 `model`、`apiUrl`、`apiKey`，分别对应模型、Base URL、API Key；服务标识保存在 `service`，额外参数保存在 `extraData`。内置服务保存实际选项值；自定义服务保存用户填写的名称，由 Server 路由到已有的 `openaicompatible`，不新增引擎服务类型。
以下字段说明以 `server/pdf2zh_server/providers/catalog.py` 的 `pdf2zh_next_config_map` 为依据，对照上游 `pdf2zh_next` 的 `translate_engine_model.py`。普通业务参数继续按原字段名从 `extraData` 写入引擎配置。
插件 LLM 编辑器按服务商、API Key、Base URL、模型、请求头、请求体六块显示；服务商、Key、URL 各用一个输入框，模型与获取按钮同行。请求头和请求体默认折叠，底部提供取消与保存并使用。“请求体”展开区内保留“翻译参数”和“添加翻译参数”入口，原业务字段继续保存在 `extraData` 并传递，JSON mode 默认关闭。

## 插件 → Server → PDFMathTranslate-next 的参数边界

本文的 `pdf2zh_next` 是 PDFMathTranslate-next 的 Python 包与命令入口。插件负责保存和选择 LLM 配置，Server 负责将插件字段转换为引擎配置并启动翻译，引擎负责读取配置、调用翻译器和生成 PDF。本节描述翻译提交的参数流转；编辑器的模型目录 GET 见文末，不经过此执行链。

1. `settings/translationConfig.ts` 的 `getTranslationConfig()` 使用 `next_service` 确定当前服务商；`next_service` 保存服务商的选项值，界面显示标签不参与服务匹配。
2. `sendRequest()` 由 `getActiveLLMApiConfig(service)` 查找 `activate = true` 且 `llmApi.service == service` 的配置。返回的 `{service, model, apiKey, apiUrl, extraData}` 放入请求的 `llm_api`；没有同服务激活配置时，请求不附带 `llm_api`。其他服务的激活配置不会替代当前选择。
3. Server 的 `Config` 先依据 `engine` 和 `next_service` 确定执行服务；`next_service` 为空时沿用请求的 `service`，再使用现有默认值。`llm_api.service` 用于确认自定义服务与当前选择同名，`llm_api` 内的模型、地址、密钥和额外参数用于填充该服务的配置。
4. 内置服务通过 `config_map.py` 的别名表映射；自定义服务通过 `provider_routing.py` 使用 `openaicompatible` 执行。`config.py` 将基础字段映射到 `[<执行服务>_detail]` 中对应的上游字段，普通 `extraData` 按原字段名写入。基础字段为空时保留该节已有值；布尔业务字段转换为 TOML 布尔值，`num_predict` 转换为整数。
5. `openai`、`openaicompatible` 的五个 `zotero_*` 请求设置由 `relay_options.py` 在写 TOML 前取出，随本次任务的 `relay_options.json` 传给 Python 引擎。`server.py` 使用 `--<执行服务>` 和 `--config-file <本次任务的 config.toml>` 启动引擎；需要中转设置时，运行入口在引擎进程中安装 `relay_patch.py`，由请求头、请求体模块构造请求并收取译文。

主设置的 `next_service` 决定使用哪个服务；LLM 管理器的 `selectedKey` 只标记当前操作条目，选中一行不会切换翻译服务或激活状态。同一 `service` 最多一条配置激活，不同 `service` 可以各有激活配置。执行“保存并使用”时会将该条目激活，并将主设置切换为 `engine = pdf2zh_next`、`next_service = 该条目的 service`；单独切换条目激活状态不改变主设置的服务选择。

插件保存的 `service` 以及请求中的 `next_service`、`llm_api.service` 均保留服务商选项原值；下面的转换发生在 Server 的执行服务、TOML 节名与 CLI 参数中。自定义名称另外保存在 `Config.custom_service`，任务信息使用该名称显示。

| 插件服务商值 | Server 执行服务 / TOML 节名前缀 |
| --- | --- |
| `ModelScope` | `modelscope` |
| `openailiked` | `openaicompatible` |
| `tencent` | `tencentmechinetranslation` |
| `silicon` | `siliconflow` |
| `qwen-mt` | `qwenmt` |
| `AliyunDashScope` | `aliyundashscope` |
| `azure-openai` | `azureopenai` |

已使用上游名称的内置服务（例如 `openai`、`deepseek`、`openaicompatible`）沿用该名称。自定义服务需要服务名不属于内置服务、请求中的 `llm_api.service` 与所选服务一致且 `apiUrl` 非空；实际执行服务统一为 `openaicompatible`。

例如，插件可以提交以下配置：

```json
{
  "engine": "pdf2zh_next",
  "next_service": "实验室中转",
  "llm_api": {
    "service": "实验室中转",
    "model": "example-model",
    "apiUrl": "https://relay.example/v1",
    "apiKey": "<API Key>",
    "extraData": {
      "openai_compatible_enable_json_mode": "false",
      "zotero_api_format": "responses",
      "zotero_body_template": "minimal"
    }
  }
}
```

Server 将前三个基础字段及 JSON mode 写入 `[openaicompatible_detail]` 的 `openai_compatible_*` 字段，使用 `--openaicompatible` 执行；接口类型与模板写入本次任务的中转设置。这条配置显示为“实验室中转”，请求协议为 Responses。将 `zotero_api_format` 改为 `chat` 或 `messages` 会改变请求协议，服务名称保持不变。

## openai

**基础字段**

- openai_model
- openai_base_url
- openai_api_key

**额外字段**

- openai_timeout: Timeout (seconds) for OpenAI service
- openai_temperature: Temperature for OpenAI service
- openai_reasoning_effort: Reasoning effort for OpenAI service (minimal/low/medium/high)
- openai_enable_json_mode: Enable JSON mode for OpenAI service（默认关闭）
- openai_send_temprature: Send temperature to OpenAI service. `pdf2zh_next` intentionally keeps this historical misspelling for compatibility; the Server migrates the old `openai_send_temperature` alias automatically.
- openai_send_reasoning_effort: Send reasoning effort to OpenAI service

## deepseek

**基础字段**

- deepseek_model
- deepseek_api_key

**额外字段**

- deepseek_enable_json_mode: Enable JSON mode for DeepSeek service（默认关闭）
- deepseek_thinking_mode: DeepSeek V4 思考模式，可选 `disabled` / `enabled`
- deepseek_reasoning_effort: DeepSeek V4 思考强度，可选 `high` / `max`，仅在 `deepseek_thinking_mode = enabled` 时生效

DeepSeek 的已有业务字段通过翻译参数入口编辑，继续使用项目原有的 `extraData` 保存和传递。

Server 的实际执行策略：

- DeepSeek V4 没有显式 thinking 设置时，自动归一化为 `disabled`，避免依赖 provider 默认行为。
- `pdf2zh_next 2.9.0` 会从同名设置字段生成 `--deepseek-thinking-mode` / `--deepseek-reasoning-effort` CLI 参数。
- Server 在 API 调用前检查**本次实际执行的** `pdf2zh_next` / Windows exe 的 `--help`，而不是只检查某个环境中的版本字符串。
- 运行时支持时，将 extraData 中的用户选择转换成上述上游 CLI 参数后执行。
- 运行时不支持时，在翻译/API 调用前直接停止，并提示用户运行 `python update_packages.py`；不会静默忽略 thinking 设置。
- 非 V4 DeepSeek 模型不会发送这两个 V4-only 参数。
- 如果旧运行时不支持这些字段，Server 会清理共享 `config.toml` 中临时写入的 thinking 字段，避免影响其他服务。

thinking 参数是否存在由 **pdf2zh_next** 决定，不由 BabelDOC 版本决定：`pdf2zh_next 2.8.2` 没有这些字段，2.9.0 才新增；BabelDOC/PyMuPDF 的版本问题属于 PDF parser 与依赖兼容问题。

上游 `pdf2zh_next` CLI 示例：

```shell
# 关闭思考（推荐作为默认配置）
uv run pdf2zh_next input.pdf \
  --deepseek \
  --deepseek-model deepseek-v4-flash \
  --deepseek-thinking-mode disabled \
  --output ./output

# 开启思考，并选择 high 强度
uv run pdf2zh_next input.pdf \
  --deepseek \
  --deepseek-model deepseek-v4-pro \
  --deepseek-thinking-mode enabled \
  --deepseek-reasoning-effort high \
  --output ./output
```

## ollama

**基础字段**

- ollama_model
- ollama_host

**额外字段**

- num_predict
  默认为2000, The max number of token to predict.

## azure-openai

**基础字段**

- azure_openai_model
- azure_openai_base_url
- azure_openai_api_key

**额外字段**

- azure_openai_api_version

## siliconflow

**基础字段**

- siliconflow_base_url
- siliconflow_model
- siliconflow_api_key

**额外字段**

- siliconflow_enable_thinking: Enable thinking for SiliconFlow service
- siliconflow_send_enable_thinking_param: Send enable thinking param for SiliconFlow service
- siliconflow_enable_json_mode: Enable JSON mode for SiliconFlow service（默认关闭）

## siliconflowfree

**额外字段**

- siliconflow_free_enable_json_mode: Enable JSON mode for SiliconFlow Free service（默认关闭）

## qwen-mt

**基础字段**

- qwenmt_model
- qwenmt_base_url
- qwenmt_api_key

**额外字段**

- ali_domains

## openailiked/openaicompatible

**基础字段**

- openai_compatible_model
- openai_compatible_base_url
- openai_compatible_api_key

**额外字段**

- openai_compatible_timeout
- openai_compatible_temperature
- openai_compatible_reasoning_effort
- openai_compatible_send_temperature
- openai_compatible_send_reasoning_effort
- openai_compatible_enable_json_mode（默认关闭）

**自定义中转字段（本仓库扩展，上游没有）**

插件编辑器的请求头和请求体默认折叠，展开后用 Key / Value 行填写。请求体使用一个选择框组合 Chat Completions、Responses、Messages 与标准、最少字段、流式三种模板，共九个选项；保存时仍拆为 `zotero_api_format` 与 `zotero_body_template`。普通业务参数通过翻译参数入口编辑，与这五项请求设置分开收集。请求头和请求体分别保存为 `zotero_extra_headers`、`zotero_extra_body` 的 JSON 对象字符串，Server 的对应解析函数也接受 JSON 对象。翻译提交时，Server 的 `relay_options.py` 在写 TOML 前取出这五项设置；`request_headers.py`、`request_body.py` 构造翻译请求，`relay_patch.py` 负责引擎接线与响应收取。对 `openai`、`openailiked` / `openaicompatible` 和自定义服务名可用，需要 Python 引擎；启用 Windows 独立 EXE 时无法加载这些翻译中转设置。

其他使用原生接口的内置服务会显示适用范围提示，停用自定义请求头编辑并隐藏自定义请求体编辑；下方翻译参数仍可编辑，已保存的五项请求设置按原值保留。翻译参数中未编辑的旧值也保留原有类型，不因打开并保存编辑器而统一转成字符串。

- zotero_api_format: 接口类型，`chat`（默认，`/chat/completions`）/ `responses`（`/v1/responses`）/ `messages`（Anthropic `/v1/messages`）
- zotero_extra_headers: 自定义请求头，JSON 对象，例如 `{"User-Agent": "my-client/1.0"}`；值写 `null` 表示不发送该默认请求头
- zotero_extra_body: 额外请求体字段，JSON 对象，例如 `{"stream": true}`；Chat、Responses、Messages 均支持流式收取
- zotero_auth_mode: `auto`（跟随接口类型）、`bearer`、`x-api-key`
- zotero_body_template: `standard`、`minimal`、`stream`；最少字段模板省略引擎的可选请求字段，保留用户明确添加的额外请求体

`zotero_api_format` 来自 `llm_api.extraData`，与服务商显示名称独立。未填写时使用 `chat`；Chat、标准模板、默认鉴权且没有自定义请求头或请求体时，`relay_options.py` 返回空设置，沿用引擎原有请求流程。已有接口别名由 `parse_api_format()` 归一化：

| 最终接口类型 | 接受的已有别名 |
| --- | --- |
| `chat` | `chat/completions`、`chat_completions`、`completions`、`openai` |
| `responses` | `response`、`codex` |
| `messages` | `message`、`anthropic`、`claude` |

接口值解析时去除首尾空白、首尾 `/` 和开头的 `v1/`，并转换为小写。这里的 `openai`、`codex`、`claude` 等是接口字段的别名，服务商名称仍按上面的服务路由处理。

翻译请求 URL 的拼接规则：

- `responses`：`<Base URL>/responses`，所以 Base URL 一般以 `/v1` 结尾
- `messages`：Base URL 以版本段（如 `/v1`、`/v2`、`/v1beta`）结尾时拼 `/messages`，否则拼 `/v1/messages`
- Base URL 已经以 `/responses` 或 `/messages` 结尾时原样使用

鉴权请求头：`zotero_auth_mode = auto` 时，`chat` 和 `responses` 发 `Authorization: Bearer <key>`，`messages` 发 `x-api-key: <key>`；显式设置 `bearer` 或 `x-api-key` 时按该设置生成鉴权头。`messages` 另带 `anthropic-version: 2023-06-01`。随后按不区分大小写的请求头名称应用 `zotero_extra_headers`：同名值覆盖默认值，`null` 移除该头；数字和布尔值转换为字符串发送。`messages` 的 `max_tokens` 默认 8192，可用 `zotero_extra_body` 修改。

请求体保留 JSON 值的类型，包括 `0`、`false`、`null`、数组与嵌套对象；这里的 `null` 表示发送 JSON null，不表示删除字段。编辑器中的点路径字段（例如 `reasoning.summary`）保存为嵌套对象（`{"reasoning":{"summary":"auto"}}`），不向接口发送带点的键名。

由 `request_body.py` 构造请求时，先生成协议基础字段和模板允许的引擎字段，再合并引擎 `options.extra_body`，最后合并编辑器的 `zotero_extra_body`，后者优先。`reasoning`、`text`、`response_format`、`output_config`、`stream_options`、`prompt_cache_options` 在双方都是对象时递归合并，其余同名字段整体覆盖。因此补充 `reasoning.summary` 会保留已有 `reasoning.effort`；显式 `{"temperature":0,"stream":false,"metadata":null}` 也会保留原值。`minimal` 省略可选引擎字段，但仍合并两处明确的额外请求体；`stream` 先设 `stream = true`，随后仍可被明确的额外字段覆盖。Chat 标准模板的非流式请求沿用上游 SDK 路径，在现有引擎 `extra_body` 上覆盖编辑器的同名顶层字段。

## 自定义服务名

pdf2zh_next 引擎下，服务名不是内置服务、且插件里有一条同名并填写了 Base URL 的激活配置时，`provider_routing.py` 将其交给 `openaicompatible` 执行。服务名用于显示与配置选择，API 协议由 `zotero_api_format` 决定。可用字段与 openailiked 相同（`openai_compatible_*` 和上面五个 `zotero_*`）。保存时同步主设置选项；保存并使用时激活并切换；正在使用的配置改名后，主设置跟随新名称。

## AliyunDashScope

**基础字段**

- aliyun_dashscope_model
- aliyun_dashscope_base_url
- aliyun_dashscope_api_key

**额外字段**

- aliyun_dashscope_timeout
- aliyun_dashscope_temperature
- aliyun_dashscope_send_temperature
- aliyun_dashscope_enable_json_mode（默认关闭）

## modelscope / zhipu / gemini / grok / groq

**额外字段**

- modelscope_enable_json_mode
- zhipu_enable_json_mode
- gemini_enable_json_mode
- grok_enable_json_mode
- groq_enable_json_mode

以上 JSON mode 字段均默认关闭；已有值继续按原业务配置传递。

## 功能模块与接线

| 功能 | 插件模块 | Server 模块 |
| --- | --- | --- |
| 服务商保存、激活与选项同步 | `settings/apiConfigurations.ts`、`apiTable.ts` | `providers/routing.py` |
| 翻译配置与激活配置传递 | `settings/translationConfig.ts`、`translation/workflow.ts` | `configuration/request.py`、`providers/catalog.py` |
| 请求头、认证、覆盖与恢复 | `settings/api-editor/requestHeaders.js` | `providers/request_headers.py` |
| 请求体模板、类型和嵌套字段 | `settings/api-editor/requestBody.js` | `providers/request_body.py` |
| 插件直连模型目录 | `settings/api-editor/models.js` | 不经过 Server |
| Server 保留的模型目录接口 | — | `api.py`、`providers/models.py` |
| 原有业务参数编辑与请求设置分离 | `settings/api-editor/parameters.js` | `providers/relay_options.py` |
| 任务输入、输出和配置隔离 | `translation/serverClient.ts` | `tasks/workspace.py` |

插件数据与控制器位于 `plugin/src/settings/`。原生资源位于 `plugin/addon/content/settings/`；`api-editor/editor.xhtml` 只负责结构，`editor.js` 显式组装预设、参数、请求头、请求体和模型模块。Server 模块位于 `server/pdf2zh_server/`，请求解析与持久化分开，协议适配由 `providers/relay_patch.py` 调用请求构造模块。

插件点击“获取”时，通过 `Zotero.HTTP.request` 直接向服务商发起模型目录 GET，不依赖 Server。请求读取当前未保存草稿中的 `service`、`apiUrl`、`apiKey`，以及请求设置里的 `zotero_api_format`、`zotero_auth_mode`、`zotero_extra_headers`；不改读已保存的激活配置，也不收集翻译请求体、模板或普通翻译参数。模型目录获取只更新候选列表并保留当前模型输入，不保存或激活配置，不切换 `next_service`，也不启动翻译引擎。

以下地址适配仅用于模型目录 GET，翻译执行服务仍按前文路由：

- 普通目录在 URL 路径上移除结尾的 `/chat/completions`、`/responses` 或 `/messages`，再拼接 `/models`；已以 `/models` 结尾时沿用。保留查询参数，移除片段标识。
- Xinference 或非 Gemini 的 Messages 接口，路径未以版本段（如 `/v1`、`/v2`、`/v1beta`）结尾时，先补 `/v1` 再拼 `/models`。
- Ollama 从根路径、`/api`、已有 `/api/tags`、`/api/generate`、`/api/chat`、`/v1`、`/v1/models` 或 `/v1/chat/completions` 路径归一到 `/api/tags`。
- Gemini 原生目录沿用版本路径拼 `/models`；自动认证使用 `x-goog-api-key`，URL 路径含 `/openai` 时使用 Bearer。显式认证模式和自定义同名请求头继续生效，不额外向查询参数写入 Key。

插件对 HTTP 401、403、404 分别提示检查认证、目录权限或目录地址；其他 HTTP 状态显示实际状态码，连接失败、20 秒超时和非 JSON 响应分别提示地址、网络或接口地址问题。已标记为没有 HTTP 模型目录的内置服务直接提示使用已有候选或手填模型；成功响应未识别到列表时也可继续手填。目录获取失败不用于判定翻译配置一定不可用。

Server 仍保留 `POST /api/llm-api/models`，供直接调用该接口的请求使用，接收 `{service, apiUrl, apiKey, extraData}`，成功返回 `{status: "success", models: [...]}`。其中 `extraData` 的接口类型、认证方式和自定义请求头用于构造模型目录 GET；不发送翻译请求体，`model` 不参与目录查询。该接口独立于插件的直连“获取”按钮；翻译提交仍按主设置选择的服务查找激活配置并下发 `llm_api`。

Server 模型目录接口采用同一套地址适配，失败时返回 `{status: "error", message: "..."}`：服务商 HTTP 错误保留对应状态码，并为 401、403、404、429 提供认证、权限、目录不存在和频率或额度提示；非 JSON 响应和连接错误返回 502，超时异常返回 504，其余参数解析错误沿用 400。没有 HTTP 模型目录或 URL 为空时返回可理解的 400 提示。

参数解析后，普通业务字段继续走原配置映射，五个 `zotero_*` 请求字段通过 relay 设置传递。用户明确写入的额外请求体保留并覆盖默认值；Messages 的有效版本从最终请求头读取。
