# 额外参数说明

本文档对应 Zotero PDF2zh **v4.1.9-beta.5**（含此前版本功能）。

LLM API 编辑器保留服务商、API Key、Base URL、模型、请求头和请求体六块。
服务商从原生下拉中选择内置站点或已保存的自定义名称；选择「自定义服务商」后可填写自己的名称。URL 和模型既可直接填写，也可从下拉中选择；API Key 单独填写，模型输入与「获取模型」按钮同行。
请求头和请求体默认折叠，底部提供「取消」和「保存并使用」。
超时、温度、思考强度等原有业务参数在「请求体」分区内的「翻译参数」中编辑，继续使用原来的字段保存和传递。

主设置的「翻译服务」与编辑器的「服务商」使用同一份服务目录，包括内置服务与已保存的自定义名称。服务名是查找和激活配置的标识，API 协议单独保存在 `extraData` 中。选择内置站点、选择已保存的自定义服务或填写自定义名称时，会更新模型、URL 的候选项，保留已经填写的 API Key、模型、自定义 URL、请求头和请求体；切换内置站点时，URL 为空或仍为上一个站点的默认地址才会跟随新站点的默认地址。修改服务名不会自动切换 API 协议，切回原服务时也不需要重新填写请求头和请求体。

::: tip 参数格式
原有服务参数在「请求体」中的「翻译参数」里填写；HTTP 请求头和请求体使用各自的 Key / Value 行。下文列出的原有业务参数仍使用与配置文件相同的字段名；未设置时使用上游默认值。JSON mode 默认关闭。
:::

服务商的保存、选择和模型列表获取方式见[配置说明](./configuration.md#llm-api-配置)。

展开「请求体」，在「翻译参数」中点击「添加翻译参数」即可新增一行，可以选择当前服务支持的字段，也可以填写自定义字段名；已有行可以编辑或删除。例如，请求超时、温度发送开关、DeepSeek 思考模式与思考强度仍通过原字段配置：

| 设置位置 | 字段示例 | 保存方式 |
|---|---|---|
| 翻译参数 | `openai_timeout`、`openai_compatible_timeout` | 作为原字段保存在 `extraData` 中，由翻译引擎处理超时。 |
| 翻译参数 | `deepseek_thinking_mode`、`deepseek_reasoning_effort` | 作为原字段保存在 `extraData` 中，继续沿用 DeepSeek 的思考控制。 |
| HTTP 请求体字段 | `temperature`、`stream`、`metadata` | 合并为对象，序列化后保存在 `extraData.zotero_extra_body` 中。 |

例如，`openai_timeout=600` 应填在「翻译参数」中；直接添加到 HTTP 请求体只会成为同名 JSON 字段，不会设置翻译请求超时。已有翻译参数会加载到原参数行，可直接修改或删除，不必重新填写整份配置。

---

## OpenAI / OpenAI 兼容服务

### 基础字段

- `openai_model` / `openai_compatible_model` - 模型名称
- `openai_base_url` / `openai_compatible_base_url` - API 地址
- `openai_api_key` / `openai_compatible_api_key` - API 密钥

### 额外字段

| 参数 | 说明 | 示例值 |
|------|------|--------|
| `openai_timeout` / `openai_compatible_timeout` | 请求超时秒数 | 600 |
| `openai_temperature` / `openai_compatible_temperature` | 控制随机性，0-1 之间 | 0.3 |
| `openai_send_temprature` / `openai_compatible_send_temperature` | 是否发送 temperature 参数 | true |
| `openai_reasoning_effort` / `openai_compatible_reasoning_effort` | 推理强度 (minimal/low/medium/high) | low |
| `openai_send_reasoning_effort` / `openai_compatible_send_reasoning_effort` | 是否发送 reasoning effort 参数 | true |
| `openai_enable_json_mode` / `openai_compatible_enable_json_mode` | 是否启用 JSON mode，默认关闭 | true |

::: warning OpenAI 参数兼容拼写
`pdf2zh_next` 为了兼容历史配置，原生 OpenAI 服务仍使用拼写为 `openai_send_temprature` 的字段；这是上游有意保留的兼容字段。Server 会自动迁移旧版插件曾使用的 `openai_send_temperature`，`openai_compatible_send_temperature` 则继续使用正常拼写。
:::

### 示例配置

```text
openai_temperature=0.3
openai_send_temprature=true
```

### 接口类型与请求头

OpenAI、OpenAI 兼容服务和自定义中转在「请求体」中选择协议/模板组合，协议不再占用单独的表单区域。这些请求设置用于 `pdf2zh_next` 的 Python 引擎。在这些配置中，`zotero_api_format` 决定请求格式和端点；例如，给使用 Responses 的配置改一个服务名，协议仍为 `responses`。

部分内置服务使用各自的原生翻译接口，尚未接入通用的翻译请求头、协议和请求体设置。编辑器会显示原生接口提示，禁用通用请求头编辑，并隐藏通用请求体模板与 HTTP 字段；仍可在「翻译参数」中编辑该服务原有的业务字段。已有通用头体设置在保存时保留原值，不会因该服务暂未支持而清空，也不表示这些设置已在该服务的翻译请求中生效。需要自定义翻译协议、请求头和请求体时，可使用支持这些设置的 OpenAI 兼容或自定义中转配置。「获取模型」使用的认证与请求头单独读取，见下文说明。

| 接口类型 | 请求端点 | 自动认证头 |
|---|---|---|
| Chat Completions（`chat`） | `/chat/completions` | `Authorization: Bearer <API Key>` |
| Responses（`responses`） | `/responses` | `Authorization: Bearer <API Key>` |
| Messages（`messages`） | `/messages` | `x-api-key: <API Key>` |

Base URL 通常填写到 `/v1`。Messages 使用不含版本路径的 Base URL 时，会补成 `/v1/messages`。

默认认证方式为「自动」，认证头直接引用上方的 API Key；修改 Key 后，自动头随之更新。如果中转站要求使用另一种认证方式，可以选择 Bearer 或 `x-api-key`。无需在自定义请求头中再次填写同一份密钥。

`Content-Type: application/json` 和 `Accept` 也会自动生成。普通请求使用 `Accept: application/json`，流式请求使用 `Accept: text/event-stream`。Messages 还会生成 `anthropic-version: 2023-06-01`。自动请求头以只读行显示，使用上方 Key 的认证行不会显示真实密钥。

展开默认折叠的「请求头」后，可按以下步骤编辑：

1. 在认证方式中选择「自动」、Bearer 或 `x-api-key`。
2. 点击「添加请求头」新增一行，在 **Key** 中选择或输入请求头名称，在 **Value** 中选择建议值或手动填写。
3. 点击行末的「×」删除该自定义行。

例如：

| Key | Value |
|---|---|
| `X-Tenant` | `research` |
| `OpenAI-Project` | 服务商提供的项目标识 |

在新增的空行中选择或输入下列 Key 时，Value 会自动填入对应的建议值：

| Key | 自动建议值 |
|---|---|
| `Content-Type` | `application/json` |
| `Accept` | 普通请求为 `application/json`，流式请求为 `text/event-stream` |
| `anthropic-version` | `2023-06-01` |

自动填值只用于尚未手动编辑 Value 的新增空行，不覆盖手填值或已加载配置中的值。`Accept` 的建议值按当前是否流式请求确定；已有自定义 `Accept` 按用户填写的值发送。`User-Agent` 等其他建议项只帮助填写名称，Value 按服务商要求填写。

请求头名称不区分大小写。同名自定义行覆盖自动头，删除覆盖行后恢复自动值；其他自定义行则直接删除。

已有 `zotero_extra_headers` 中的 JSON `null` 表示不发送该请求头，加载和保存时会保留这一含义；删除这条覆盖行后，自动头恢复。请求头的数字和布尔值最终转换为 HTTP 文本值。

### 请求体模板

展开默认折叠的「请求体」后，使用一个选择框同时选择协议与模板。九个选项由三个协议和三种模板组合而成：

| 选项 | 协议保存值 | 模板保存值 |
|---|---|---|
| Chat Completions · 标准 | `chat` | `standard` |
| Chat Completions · 最少字段 | `chat` | `minimal` |
| Chat Completions · 流式 | `chat` | `stream` |
| Responses · 标准 | `responses` | `standard` |
| Responses · 最少字段 | `responses` | `minimal` |
| Responses · 流式 | `responses` | `stream` |
| Messages · 标准 | `messages` | `standard` |
| Messages · 最少字段 | `messages` | `minimal` |
| Messages · 流式 | `messages` | `stream` |

模型名称和翻译输入由当前配置及 PDF 内容自动填入。三种模板的行为为：

| 模板 | 保存值 | 行为 |
|---|---|---|
| 标准 | `standard` | 生成当前接口的基础请求，并按已保存业务参数的发送开关带上温度、思考强度、JSON mode 等选项。 |
| 最少字段 | `minimal` | 生成模型、翻译输入等接口必需字段，暂不带上原业务参数中的可选请求字段；原配置值仍保留。 |
| 流式 | `stream` | 在标准模板基础上设置 `stream: true`，使用流式响应。 |

最少字段模板仍会应用用户明确填写的额外请求体。Messages 的必需输出上限 `max_tokens` 也会保留。

点击「添加请求体字段」新增 Key / Value 行，在 Key 中选择或输入当前协议支持的字段名，再填写 Value；点击行末的「×」删除该字段。布尔字段使用 `false` / `true` 下拉框，数字字段使用数字输入框，字符串和枚举使用文本或建议值控件，对象和数组使用 JSON 编辑框。模板生成的字段也可以在 Value 中修改，修改后作为显式值保存。

新字段按所选字段的类型填写和保存：

| 类型 | 示例 | 实际请求中的值 |
|---|---|---|
| 布尔 | 在 `store` 的下拉框选择 `false` | `false`，不是字符串 `"false"` |
| 数字 | 在 `max_output_tokens` 的数字输入框填写 `4096` | 数字 `4096` |
| 数字零 | `temperature` 填写 `0` | 数字 `0`，不会当作未设置 |
| 字符串或枚举 | `reasoning.effort` 填写或选择 `low` | 字符串 `"low"` |
| JSON | `metadata` 填写 `{"task":"paper"}` | JSON 对象；数组同样按 JSON 保存 |
| 空值 | 已有额外请求体中的 `metadata: null` | JSON `null`，不会当作未设置或字符串 `"null"` |

已有配置中的字符串继续按字符串编辑和保存，即使字段名通常对应布尔或数字也不自动转换。例如 `{"store":"false","max_output_tokens":"4096"}` 普通加载和保存后仍保留两个字符串；它们与布尔 `false`、数字 `4096` 的含义不同。如需改用布尔或数字，可删除该行，再新增同名字段并使用对应控件填写。

带点的字段名表示嵌套结构。例如 `reasoning.effort=low` 与 `reasoning.summary=auto` 会组合成：

```json
{
  "reasoning": {
    "effort": "low",
    "summary": "auto"
  }
}
```

额外请求体在模板和原参数之后应用，**当前显式填写的值最后覆盖同名字段**。常用嵌套配置会合并，未覆盖的子字段继续保留。

加载已有配置并普通保存时，保留显式填写的 `stream`。例如，原配置同时保存了流式模板和 `zotero_extra_body` 中的 `{"stream":false}`，没有主动切换模板时，最终请求仍使用 `stream: false`。

主动切换标准、最少字段或流式模板时，`stream` 跟随所选模式：标准模板设置 `stream: false`，流式模板设置 `stream: true`，最少字段模板移除原有 `stream`，不自动添加该字段。切换模式会重设旧的显式 `stream`，其他显式请求体字段保留。

`0`、`false` 和 `null` 都是已设置的请求体值，普通加载、编辑和保存时保留其 JSON 类型，Server 应用覆盖时也会保留；主动切换模板时的 `stream` 按上述模式规则处理。嵌套对象不会被转成普通字符串；上例中的 `reasoning.effort` 与 `reasoning.summary` 仍在同一个 `reasoning` 对象中。

### 原配置的保存格式

紧凑界面仍使用原来的 `extraData` 保存和传递，没有引入另一套插件配置。合并选择框保存时拆成协议与模板两个原字段；认证方式、自定义请求头和额外请求体也存入同一个 `extraData`，原服务参数继续保留原字段名：

| `extraData` 字段 | 保存内容 | Server 请求设置 |
|---|---|---|
| `zotero_api_format` | `chat`、`responses` 或 `messages` | `api_format` |
| `zotero_auth_mode` | `auto`、`bearer` 或 `x-api-key` | `auth_mode`；默认 `auto` |
| `zotero_body_template` | `standard`、`minimal` 或 `stream` | `body_template`；默认 `standard` |
| `zotero_extra_headers` | 自定义请求头的 JSON 字符串，内容为对象 | 解析为 `headers` 对象 |
| `zotero_extra_body` | 额外请求体的 JSON 字符串，内容为对象 | 解析为 `extra_body` 对象 |

旧版保存的 JSON 字符串会加载成可编辑的 Key/Value 行，保存时继续序列化为 JSON 字符串。自动认证头不重复写入自定义请求头；原来的 `openai_timeout`、`openai_send_temprature` 等业务参数在「翻译参数」中编辑，仍按原字段保存到同一个 `extraData`，不因界面折叠而清空。

翻译时，插件按主设置中的服务名找到该服务已激活的配置，将 `service`、`apiKey`、`apiUrl`、`model` 和 `extraData` 一起放入请求的 `llm_api`。Server 将自定义服务名路由到 OpenAI 兼容引擎，保留原名称用于识别配置；请求协议继续取自 `extraData`。`relay_options.py` 取出上表的五个请求字段，其他业务参数继续交给原引擎配置处理。取出的设置随本次任务传给 Python 引擎，由 `request_headers.py` 生成最终请求头、`request_body.py` 合并最终请求体；这五个扩展字段不会直接写入上游的 `config.toml`。

填写或修改连接信息后，可直接点击「获取模型」，无需先保存。模型列表由 Zotero 直接向服务商查询，使用**当前尚未保存**的服务名、URL、API Key、协议、认证方式和自定义请求头，不依赖 Server 的模型查询接口。模型获取单独读取连接信息和请求头，不解析 HTTP 请求体；即使请求体中的 JSON 尚未填写完整，也可以先查询模型。

返回的模型加入当前模型候选项，保留手填的模型名称；该查询不发送翻译请求体，也不会保存或激活配置。模型列表是否开放取决于服务商接口，查询失败时仍可手动填写模型名称。

---

## DeepSeek

DeepSeek V4 模型（包括 `deepseek-v4-pro` 和 `deepseek-v4-flash`）支持显式控制思考模式。由于开启思考会产生额外 reasoning token 与费用，Zotero PDF2zh 默认关闭 DeepSeek 思考模式。

### 基础字段

- `deepseek_model` - 模型名称，例如 `deepseek-v4-pro` 或 `deepseek-v4-flash`
- `deepseek_api_key` - API 密钥

### 额外字段

| 参数 | 说明 | 可选值 / 默认值 |
|------|------|-----------------|
| `deepseek_thinking_mode` | 是否开启 DeepSeek V4 思考模式 | `disabled` / `enabled`，默认 `disabled` |
| `deepseek_reasoning_effort` | 思考强度，仅在思考模式开启时生效 | `high` / `max`，开启后默认 `high` |
| `deepseek_enable_json_mode` | 是否启用 JSON mode | 依 `pdf2zh_next` 配置 |

展开「请求体」，即可在其中的「翻译参数」里添加或编辑这些字段。它们仍然使用插件原有的 `extraData` 保存和传递，已有配置继续生效；无需将思考控制字段放进 `zotero_extra_body`。

### 实际执行方式

`pdf2zh_next 2.9.0` 在 `DeepSeekSettings` 中新增了 `deepseek_thinking_mode` 和 `deepseek_reasoning_effort`，对应 CLI 参数为：

```text
deepseek_thinking_mode     -> --deepseek-thinking-mode
deepseek_reasoning_effort  -> --deepseek-reasoning-effort
```

Zotero PDF2zh v4.1.0 起的保护流程（v4.1.1 相同）：

1. 插件通过 `extraData` 保存用户选择；
2. DeepSeek V4 没有显式设置时，Server 自动使用 `disabled`；
3. 对 uv / conda / system Python，Server 从**本次实际 Python 环境中已安装的 `pdf2zh_next` distribution metadata/source**静态确认 Thinking capability，不启动重型 `pdf2zh_next --help`；
4. 支持时，将用户选择转换为上游正式 CLI 参数；
5. 默认不思考且 runtime 不支持思考控制时，去掉这些字段并放行翻译；
6. 用户手动开启思考但 runtime 不支持时，在任何翻译 API 调用之前停止并提示更新；
7. Windows standalone exe 无法通过 Python distribution 静态检查时，才使用独立的 exe capability 检查；
8. 非 DeepSeek V4 不发送这些 V4-only 参数。

::: warning 为什么不执行 pdf2zh_next --help？
`pdf2zh_next 2.9.0` 在 CLI 参数解析前可能加载 BabelDOC / high-level 模块，因此 `--help` 并不是轻量健康检查，在部分机器上可能需要很长时间。v4.1.0 的正常 Python 环境路径改为静态检查，避免把一个已经安装成功的环境误判成失败。
:::

::: warning 版本与 BabelDOC 的区别
DeepSeek V4 thinking 控制由 **`pdf2zh_next` 运行时**提供，而不是由 BabelDOC 版本决定。`pdf2zh_next 2.8.2` 没有这两个字段；`pdf2zh_next 2.9.0` 才加入。BabelDOC / PyMuPDF 主要影响 PDF 解析和依赖兼容性。
:::

上游 CLI 示例：

```bash
# 推荐默认：关闭思考
uv run pdf2zh_next input.pdf \
  --deepseek \
  --deepseek-model deepseek-v4-flash \
  --deepseek-thinking-mode disabled \
  --output ./output

# 开启思考，并使用 high 强度
uv run pdf2zh_next input.pdf \
  --deepseek \
  --deepseek-model deepseek-v4-flash \
  --deepseek-thinking-mode enabled \
  --deepseek-reasoning-effort high \
  --output ./output
```

---

## Ollama

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `num_predict` | 最大预测 token 数 | 2000 |

## Azure OpenAI

| 参数 | 说明 |
|------|------|
| `azure_openai_api_version` | API 版本 |

## SiliconFlow

| 参数 | 说明 |
|------|------|
| `siliconflow_enable_thinking` | 启用思考模式 |
| `siliconflow_send_enable_thinking_param` | 是否发送思考模式参数 |
| `siliconflow_enable_json_mode` | 是否启用 JSON mode，默认关闭 |

## SiliconFlow Free

| 参数 | 说明 |
|------|------|
| `siliconflow_free_enable_json_mode` | 是否启用 JSON mode，默认关闭 |

## Qwen MT

| 参数 | 说明 |
|------|------|
| `ali_domains` | Qwen MT 的领域/上下文提示 |

## 使用建议

1. 布尔值使用 `true` / `false`。
2. 可选参数不确定时留空，使用上游默认值。
3. 服务 API 和模型参数会变化；遇到参数被拒绝时，应同时核对当前 `pdf2zh_next` 版本和上游文档。

::: info 相关文档
- [配置说明](/zh/guide/configuration)
- [翻译环境更新](/zh/guide/package-update)
- [翻译服务问题](/zh/guide/faq/translation-service)
:::
