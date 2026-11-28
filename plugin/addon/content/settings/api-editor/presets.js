/* eslint-disable no-restricted-globals */
/* global window */
(() => {
    "use strict";
    const CUSTOM_SERVICE_OPTION = "__custom_service__";
    const DEFAULT_SERVICES = {
        openailiked: {
            name: "OpenAI-Liked",
            models: [
                // deepseek
                "deepseek-v3-2-251201",
                "deepseek-v3-1-terminus",
                "deepseek-v3-1-250821", // 即将下线
                "deepseek-v3-250324",
                "deepseek-r1-250528",
                // kimi
                "kimi-k2-250905",
                // glm
                "glm-4-7-251222",
                // doubao 1.6
                "doubao-seed-1-6-251015",
                "doubao-seed-1-6-250615",
                "doubao-seed-1-6-flash-250615",
                "doubao-seed-1-6-thinking-250715", // 即将下线
                "doubao-seed-1-6-thinking-250615", // 即将下线
                "doubao-seed-translation-250915",
                // doubao 1.8
                "doubao-seed-1-8-251228",
                // doubao 2.0
                "doubao-seed-2-0-pro-260215",
                "doubao-seed-2-0-lite-260215",
                "doubao-seed-2-0-mini-260215",
                "doubao-seed-2-0-code-preview-260215",
                // doubao 1.5
                "doubao-1-5-lite-32k-250115",
                "doubao-1-5-thinking-pro-250415", // 即将下线
            ],
            urls: ["https://ark.cn-beijing.volces.com/api/v3"],
            modelListUrl:
                "https://console.volcengine.com/ark/region:ark+cn-beijing/openManagement?LLM=%7B%7D&advancedActiveKey=model",
            extraData: [],
        },
        openai: {
            name: "OpenAI",
            models: [
                "gpt-5",
                "gpt-5-mini",
                "gpt-4",
                "gpt-4",
                "gpt-4o",
                "gpt-4o-mini",
            ],
            urls: ["https://api.openai.com/v1"],
            modelListUrl: "https://platform.openai.com/docs/models",
        },
        AliyunDashScope: {
            name: "AliyunDashScope",
            models: [
                "qwen3.5-plus",
                "qwen3.5-flash",
                "qwen3.5-35b-a3b",
                "qwen3-max",
                "qwen-plus",
                "qwen-flash",
                "qwen-mt-plus",
                "qwen-mt-flash",
            ],
            urls: ["https://dashscope.aliyuncs.com/compatible-mode/v1"],
        },
        silicon: {
            name: "SiliconFlow",
            models: [
                "deepseek-ai/DeepSeek-V3.2",
                "deepseek-ai/DeepSeek-V3.1-Terminus",
                "deepseek-ai/DeepSeek-R1",
                "Pro/deepseek-ai/DeepSeek-V3.2",
                "Pro/deepseek-ai/DeepSeek-V3.1-Terminus",
                "Pro/deepseek-ai/DeepSeek-R1",
                "Qwen/Qwen3-8B",
                "Qwen/Qwen2.5-72B-Instruct",
                "moonshotai/Kimi-K2-Thinking",
                "Pro/zai-org/GLM-4.7",
            ],
            urls: ["https://api.siliconflow.cn/v1"],
            modelListUrl: "https://cloud.siliconflow.cn/me/models",
        },
        gemini: {
            name: "Gemini",
            models: [
                "gemini-3.0-flash-preview",
                "gemini-3.0-pro-preview",
                "gemini-2.5-flash",
                "gemini-2.5-pro",
            ],
            urls: ["https://generativelanguage.googleapis.com/v1beta/openai"],
        },
        "azure-openai": {
            name: "Azure OpenAI",
            models: [
                "gpt-5",
                "gpt-5-mini",
                "gpt-4",
                "gpt-4",
                "gpt-4o",
                "gpt-4o-mini",
            ],
        },
        zhipu: {
            name: "Zhipu",
            models: [
                "glm-4-flash",
                "glm-4.5",
                "glm-4.5-x",
                "glm-4.5-air",
                "glm-4.5-airx",
            ],
            urls: ["https://open.bigmodel.cn/api/paas/v4"],
        },
        deepseek: {
            name: "DeepSeek",
            models: ["deepseek-flash", "deepseek-v4-pro", "deepseek-v4-flash"],
            urls: ["https://api.deepseek.com/v1"],
            modelListUrl: "https://platform.deepseek.com/",
        },
        "qwen-mt": {
            name: "Qwen",
            models: [
                "qwen-plus-latest",
                "qwen-max",
                "qwen-max-latest",
                "qwen-plus",
                "qwen3-235b-a22b",
            ],
            urls: ["https://dashscope.aliyuncs.com/compatible-mode/v1"],
        },
        ollama: {
            name: "Ollama",
            models: ["gemma3:12B", "gemma"],
            urls: ["http://localhost:11434"],
            modelListUrl: "https://ollama.com/library",
        },
        modelscope: {
            name: "ModelScope",
            models: ["openai-mirror/gpt-oss-120b", "openai-mirror/gpt-oss-20b"],
            urls: ["https://api-inference.modelscope.cn/v1"],
        },
        tencent: {
            name: "TencentMechineTranslation",
        },
        grok: {
            name: "Grok",
            models: ["grok-4-0709", "grok-3", "grok-3-mini"],
            urls: ["https://api.x.ai/v1"],
        },
        groq: {
            name: "Groq",
            urls: ["https://api.groq.com/openai/v1"],
        },
        azure: {
            name: "Azure",
            urls: ["https://api.translator.azure.cn"],
        },
        xinference: {
            name: "XInference",
            models: ["gemma-2-it"],
            urls: ["http://127.0.0.1:9997"],
        },
        deepl: {
            name: "DeepL",
        },
        claudecode: {
            name: "Claude Code",
            models: ["sonnet"],
            urls: ["claude"],
        },
    };

    const DEEPSEEK_THINKING_FIELDS = {
        deepseek_thinking_mode: {
            values: ["disabled", "enabled"],
            defaultValue: "disabled",
            titleKey: "deepseekThinkingModeTitle",
        },
        deepseek_reasoning_effort: {
            values: ["low", "high", "max"],
            defaultValue: "high",
            titleKey: "deepseekReasoningEffortTitle",
        },
    };
    // Keep in sync with server/utils/config_map.py pdf2zh_next extraData.
    const PDF2ZH_NEXT_SERVICE_ALIASES = {
        ModelScope: "modelscope",
        openailiked: "openaicompatible",
        tencent: "tencentmechinetranslation",
        silicon: "siliconflow",
        "qwen-mt": "qwenmt",
        AliyunDashScope: "aliyundashscope",
        "azure-openai": "azureopenai",
    };
    const REASONING_EFFORT_VALUES = [
        "none",
        "minimal",
        "low",
        "medium",
        "high",
        "xhigh",
        "max",
    ];
    const PDF2ZH_NEXT_EXTRA_FIELDS = {
        openai: [
            {
                key: "openai_timeout",
                type: "string",
                zh: "超时秒数",
                en: "Timeout (seconds)",
            },
            {
                key: "openai_temperature",
                type: "string",
                zh: "温度",
                en: "Temperature",
            },
            {
                key: "openai_reasoning_effort",
                type: "enum",
                values: REASONING_EFFORT_VALUES,
                zh: "推理强度（none 仅部分模型支持）",
                en: "Reasoning effort (none: select models only)",
            },
            {
                key: "openai_enable_json_mode",
                type: "bool",
                zh: "JSON 模式（默认关闭）",
                en: "JSON mode (off by default)",
            },
            {
                key: "openai_send_temprature",
                type: "bool",
                zh: "发送 temperature（上游拼写 temprature）",
                en: "Send temperature (upstream spelling)",
            },
            {
                key: "openai_send_reasoning_effort",
                type: "bool",
                zh: "发送 reasoning effort",
                en: "Send reasoning effort",
            },
        ],
        aliyundashscope: [
            {
                key: "aliyun_dashscope_timeout",
                type: "string",
                zh: "超时秒数",
                en: "Timeout (seconds)",
            },
            {
                key: "aliyun_dashscope_temperature",
                type: "string",
                zh: "温度",
                en: "Temperature",
            },
            {
                key: "aliyun_dashscope_send_temperature",
                type: "bool",
                zh: "发送 temperature",
                en: "Send temperature",
            },
            {
                key: "aliyun_dashscope_enable_json_mode",
                type: "bool",
                zh: "JSON 模式（默认关闭）",
                en: "JSON mode (off by default)",
            },
        ],
        ollama: [
            {
                key: "num_predict",
                type: "string",
                zh: "最大预测 token 数",
                en: "Max predicted tokens",
            },
        ],
        azureopenai: [
            {
                key: "azure_openai_api_version",
                type: "string",
                zh: "API 版本",
                en: "API version",
            },
        ],
        modelscope: [
            {
                key: "modelscope_enable_json_mode",
                type: "bool",
                zh: "JSON 模式（默认关闭）",
                en: "JSON mode (off by default)",
            },
        ],
        zhipu: [
            {
                key: "zhipu_enable_json_mode",
                type: "bool",
                zh: "JSON 模式（默认关闭）",
                en: "JSON mode (off by default)",
            },
        ],
        siliconflow: [
            {
                key: "siliconflow_enable_thinking",
                type: "bool",
                zh: "启用思考",
                en: "Enable thinking",
            },
            {
                key: "siliconflow_send_enable_thinking_param",
                type: "bool",
                zh: "发送思考参数",
                en: "Send thinking parameter",
            },
            {
                key: "siliconflow_enable_json_mode",
                type: "bool",
                zh: "JSON 模式（默认关闭）",
                en: "JSON mode (off by default)",
            },
        ],
        siliconflowfree: [
            {
                key: "siliconflow_free_enable_json_mode",
                type: "bool",
                zh: "JSON 模式（默认关闭）",
                en: "JSON mode (off by default)",
            },
        ],
        gemini: [
            {
                key: "gemini_enable_json_mode",
                type: "bool",
                zh: "JSON 模式（默认关闭）",
                en: "JSON mode (off by default)",
            },
        ],
        grok: [
            {
                key: "grok_enable_json_mode",
                type: "bool",
                zh: "JSON 模式（默认关闭）",
                en: "JSON mode (off by default)",
            },
        ],
        groq: [
            {
                key: "groq_enable_json_mode",
                type: "bool",
                zh: "JSON 模式（默认关闭）",
                en: "JSON mode (off by default)",
            },
        ],
        deepseek: [
            {
                key: "deepseek_enable_json_mode",
                type: "bool",
                zh: "JSON 模式（默认关闭）",
                en: "JSON mode (off by default)",
            },
            {
                key: "deepseek_thinking_mode",
                type: "enum",
                values: ["disabled", "enabled"],
                zh: "思考模式",
                en: "Thinking mode",
            },
            {
                key: "deepseek_reasoning_effort",
                type: "enum",
                values: ["low", "high", "max"],
                zh: "思考强度",
                en: "Reasoning effort",
            },
        ],
        qwenmt: [
            {
                key: "ali_domains",
                type: "string",
                zh: "领域提示",
                en: "Domain hint",
            },
        ],
        openaicompatible: [
            {
                key: "openai_compatible_timeout",
                type: "string",
                zh: "超时秒数",
                en: "Timeout (seconds)",
            },
            {
                key: "openai_compatible_temperature",
                type: "string",
                zh: "温度",
                en: "Temperature",
            },
            {
                key: "openai_compatible_reasoning_effort",
                type: "enum",
                values: REASONING_EFFORT_VALUES,
                zh: "推理强度（none 仅部分模型支持）",
                en: "Reasoning effort (none: select models only)",
            },
            {
                key: "openai_compatible_send_temperature",
                type: "bool",
                zh: "发送 temperature",
                en: "Send temperature",
            },
            {
                key: "openai_compatible_send_reasoning_effort",
                type: "bool",
                zh: "发送 reasoning effort",
                en: "Send reasoning effort",
            },
            {
                key: "openai_compatible_enable_json_mode",
                type: "bool",
                zh: "JSON 模式（默认关闭）",
                en: "JSON mode (off by default)",
            },
        ],
    };
    // 自定义中转: 这三项有专门的表单区域(relay-section), 不走"额外参数"行。
    // 由 Server 的 utils/relay_patch.py 处理(需 Python 引擎)。
    const RELAY_KEYS = [
        "zotero_api_format",
        "zotero_extra_headers",
        "zotero_extra_body",
        "zotero_auth_mode",
        "zotero_body_template",
    ];
    // 与 server/utils/config_map.py 的 is_known_pdf2zh_next_service 保持一致。
    // 不在这些名字里的服务名视为"自定义服务", Server 用 OpenAI 兼容引擎执行。
    const PDF2ZH_NEXT_BUILTIN_SERVICES = [
        "bing",
        "google",
        "argos",
        "clitranslator",
        "deepl",
        "xinference",
        "tencentmechinetranslation",
        "azure",
        "anythingllm",
        "dify",
        "claudecode",
    ];
    const UI_TEXT = {
        zh: {
            windowTitle: "LLM API 配置编辑器",
            customProviderName: "自定义服务商名称",
            requestAddress: "请求地址",
            serviceName: "服务商",
            servicePlaceholder: "输入服务商名称，或选择已有服务商",
            customServiceOption: "＋ 自定义服务商…",
            customServicePlaceholder: "输入自定义服务商名称",
            deleteCustomService: "删除自定义服务",
            modelName: "模型",
            modelPlaceholder: "选择或输入模型 (如: deepseek-flash)",
            deleteCustomModel: "删除自定义模型",
            apiKey: "Key",
            deleteApiKey: "删除 API Key 记录",
            baseUrl: "URL",
            deleteCustomUrl: "删除自定义 URL",
            activate: "保存后设为当前翻译配置",
            extraParams: "高级翻译参数 · 原“添加参数”",
            addParam: "+ 添加参数",
            modelList: "查看支持的模型列表",
            cancel: "取消",
            save: "保存配置",
            saveAndUse: "保存并使用",
            saveActionHint: "",
            serviceRequired: "请填写 LLM 服务名称。",
            serviceTooShort: "LLM 服务名称至少需要 3 个字符。",
            relayModelRequired: "自定义中转必须填写模型名称。",
            relayUrlRequired: "自定义中转必须填写 Base URL。",
            invalidBaseUrl: "Base URL 必须是有效的 http:// 或 https:// 地址。",
            saveFailed: "保存失败，请检查设置后重试。",
            editTitle: "编辑 LLM API 配置",
            addTitle: "添加新的 LLM API 配置",
            parameterName: "参数名",
            parameterValue: "参数值",
            selectPlaceholder: "请选择...",
            openModelList: "打开模型列表",
            deleteRecord: "删除此记录",
            cannotDelete: "无法删除",
            confirmDeleteService: "确定删除服务历史: ",
            deepseekThinkingModeTitle:
                "DeepSeek 思考模式（默认关闭以控制费用）",
            deepseekReasoningEffortTitle:
                "DeepSeek 思考强度（仅在思考模式开启时生效）",
            deprecatedDeepSeekModel:
                "deepseek-chat / deepseek-reasoner 已停止支持，请选择 DeepSeek V4 模型。",
            deepseekNonFlashSpellingAlert:
                "思考控制支持精确名称 deepseek-flash 和 deepseek-v4-* 模型（如 deepseek-v4-flash）。其他写法可能导致思考设置被忽略并产生额外费用，请检查模型名大小写。",
            extraFieldsHint:
                "当前服务支持的额外字段：{fields}。不填则使用上游默认值。点「添加参数」后从下拉列表选择，也可选「自定义」手动输入。",
            extraFieldsHintEmpty: "当前服务没有预置额外字段，仍可手动输入。",
            extraFieldUnset: "未设置（上游默认）",
            selectExtraField: "选择支持的字段...",
            customExtraField: "自定义...",
            customRelayOption: "＋ 自定义中转（自己起名）",
            serviceHint: "",
            serviceHintCustom:
                "保存后，「{name}」会出现在主设置的翻译服务选项中。",
            relayTitle: "请求设置",
            nativeRequestSettings:
                "此内置服务使用原生接口。翻译参数在下方设置；自定义协议、请求头和请求体请使用自定义服务商。已有请求设置按原值保留。",
            relayFormat: "接口类型",
            relayFormatChat: "chat — /chat/completions（默认）",
            relayFormatResponses:
                "responses — /v1/responses（OpenAI / Codex 格式）",
            relayFormatMessages: "messages — /v1/messages（Claude 格式）",
            relayFormatHint: "",
            relayHeaders: "请求头",
            relayHeadersPlaceholder:
                '{"User-Agent": "客户端名称/版本号", "x-app": "cli"}',
            relayHeadersHint:
                "JSON 格式，可留空。用来按中转站的要求设置 User-Agent 等请求头；值写 null 表示不发送该请求头。",
            relayBody: "请求体",
            relayBodyPlaceholder: '{"stream": true}',
            relayBodyHint: "",
            relayBadJson:
                '「{field}」不是合法的 JSON 对象。正确写法示例：{"名称": "值"}',
        },
        en: {
            windowTitle: "LLM API Configuration Editor",
            customProviderName: "Custom provider name",
            requestAddress: "Request URL",
            serviceName: "Provider",
            servicePlaceholder: "Select or enter a service (e.g. deepseek)",
            customServiceOption: "+ Custom provider…",
            customServicePlaceholder: "Enter a custom provider name",
            deleteCustomService: "Delete custom service",
            modelName: "Model",
            modelPlaceholder: "Select or enter a model (e.g. deepseek-flash)",
            deleteCustomModel: "Delete custom model",
            apiKey: "Key",
            deleteApiKey: "Delete API Key history",
            baseUrl: "URL",
            deleteCustomUrl: "Delete custom URL",
            activate: "Use this configuration after saving",
            extraParams: "Advanced translation parameters",
            addParam: "+ Add Parameter",
            modelList: "View Supported Models",
            cancel: "Cancel",
            save: "Save configuration",
            saveAndUse: "Save and use",
            saveActionHint: "",
            serviceRequired: "Enter an LLM service name.",
            serviceTooShort:
                "An LLM service name must have at least 3 characters.",
            relayModelRequired: "Enter a model name for the custom relay.",
            relayUrlRequired: "Enter a Base URL for the custom relay.",
            invalidBaseUrl:
                "Base URL must be a valid http:// or https:// address.",
            saveFailed: "Could not save. Check your settings and try again.",
            editTitle: "Edit LLM API Configuration",
            addTitle: "Add LLM API Configuration",
            parameterName: "Parameter name",
            parameterValue: "Parameter value",
            selectPlaceholder: "Select...",
            openModelList: "Open model list",
            deleteRecord: "Delete this record",
            cannotDelete: "Cannot delete",
            confirmDeleteService: "Delete service history: ",
            deepseekThinkingModeTitle:
                "DeepSeek thinking mode (disabled by default to control cost)",
            deepseekReasoningEffortTitle:
                "DeepSeek reasoning effort (only used when thinking is enabled)",
            deprecatedDeepSeekModel:
                "deepseek-chat / deepseek-reasoner are no longer supported. Select a DeepSeek V4 model.",
            deepseekThinkingCompatWarning:
                "Thinking control supports the exact deepseek-flash name and legacy deepseek-v4-* models. Other spellings can silently ignore the setting; check the model name and case.",
            extraFieldsHint:
                "Supported extra fields for this service: {fields}. Leave unset to use upstream defaults. Click Add, then pick from the dropdown, or choose Custom to type a key.",
            extraFieldsHintEmpty:
                "This service has no preset extra fields. You can still enter a custom key.",
            extraFieldUnset: "Unset (upstream default)",
            selectExtraField: "Select a supported field...",
            customExtraField: "Custom...",
            customRelayOption: "+ Custom relay (name it yourself)",
            serviceHint: "",
            serviceHintCustom:
                '"{name}" will appear in the main translation-service selector after saving.',
            relayTitle: "Request settings",
            nativeRequestSettings:
                "This built-in provider uses its native interface. Edit translation parameters below. Use a custom provider for custom protocols, headers, and request bodies. Existing request settings are preserved.",
            relayFormat: "API format",
            relayFormatChat: "chat — /chat/completions (default)",
            relayFormatResponses:
                "responses — /v1/responses (OpenAI / Codex format)",
            relayFormatMessages: "messages — /v1/messages (Claude format)",
            relayFormatHint: "",
            relayHeaders: "Request headers",
            relayHeadersPlaceholder:
                '{"User-Agent": "client-name/version", "x-app": "cli"}',
            relayHeadersHint:
                "JSON, optional. Sets headers such as User-Agent as your relay requires; a null value removes a header.",
            relayBody: "Request body",
            relayBodyPlaceholder: '{"stream": true}',
            relayBodyHint: "",
            relayBadJson:
                '"{field}" is not a valid JSON object. Example: {"name": "value"}',
        },
    };
    const DEPRECATED_DEEPSEEK_MODELS = new Set([
        "deepseek-chat",
        "deepseek-reasoner",
    ]);
    const TEXT = {
        zh: {
            fetchModels: "获取模型",
            fetching: "获取中…",
            fetched: (count) => `已获取 ${count} 个模型`,
            noModels: "接口返回成功，但未找到模型列表，可继续手填模型",
            baseUrlRequired: "请先填写 Base URL",
            apiKeyRequired: "该服务获取模型列表需要 API Key",
            failed: (message) => `获取失败：${message}`,
            modelListUnavailable:
                "该服务不提供模型列表接口，可使用已有候选或手填模型",
            modelUnauthorized: "站点返回 HTTP 401，请检查 Key 与认证方式",
            modelForbidden: "站点返回 HTTP 403，当前账号无权访问模型列表",
            modelNotFound:
                "站点返回 HTTP 404，该地址未提供模型列表，可手填模型",
            modelHttpError: (status) => `站点返回 HTTP ${status}`,
            modelTimeout: "模型接口请求超过 20 秒，请检查地址和网络",
            modelNetworkError: "无法连接模型接口，请检查地址和网络",
            modelNonJson: "模型接口返回的不是 JSON，请检查 URL 是否为 API 地址",
            modelSettingsError: "请检查模型接口 URL 和请求头设置",
            legacyChat:
                "旧 deepseek-chat 已迁移为 deepseek-v4-flash（思考关闭）",
            legacyReasoner:
                "旧 deepseek-reasoner 已迁移为 deepseek-v4-flash（思考开启）",
            unsupported:
                "模型列表接口可能未开放；这不代表翻译配置不可用，可手动填写模型名称。",
            badRelayHeaders: "自定义请求头必须是合法的 JSON 对象",
            badRelayHeader: "自定义请求头名称或值不合法",
            disabled: "关闭",
            enabled: "开启",
            high: "高",
            max: "最大",
        },
        en: {
            fetchModels: "Fetch models",
            fetching: "Fetching model list…",
            fetched: (count) => `Fetched ${count} models`,
            noModels:
                "The request succeeded, but no models were found. You can enter a model manually.",
            baseUrlRequired: "Enter a Base URL first",
            apiKeyRequired:
                "An API Key is required to fetch models for this service",
            failed: (message) => `Fetch failed: ${message}`,
            modelListUnavailable:
                "This service has no model-list endpoint. Use an existing option or enter a model manually.",
            modelUnauthorized:
                "The provider returned HTTP 401. Check the API Key and authentication mode.",
            modelForbidden:
                "The provider returned HTTP 403. This account cannot access the model list.",
            modelNotFound:
                "The provider returned HTTP 404. This URL has no model list; enter a model manually.",
            modelHttpError: (status) => `The provider returned HTTP ${status}.`,
            modelTimeout:
                "The model request exceeded 20 seconds. Check the URL and network.",
            modelNetworkError:
                "Cannot connect to the model endpoint. Check the URL and network.",
            modelNonJson:
                "The model endpoint did not return JSON. Check that the URL is an API address.",
            modelSettingsError:
                "Check the model endpoint URL and request headers.",
            legacyChat:
                "Legacy deepseek-chat migrated to deepseek-v4-flash (thinking disabled)",
            legacyReasoner:
                "Legacy deepseek-reasoner migrated to deepseek-v4-flash (thinking enabled)",
            unsupported:
                "The model-list endpoint may be unavailable. Translation can still work; enter a model name manually.",
            badRelayHeaders: "Custom headers must be a valid JSON object",
            badRelayHeader: "Invalid custom header name or value",
            disabled: "Disabled",
            enabled: "Enabled",
            high: "High",
            max: "Max",
        },
    };

    UI_TEXT.zh = { ...UI_TEXT.zh, ...TEXT.zh };
    UI_TEXT.en = { ...UI_TEXT.en, ...TEXT.en };

    window.LlmApiEditorPresets = {
        CUSTOM_SERVICE_OPTION,
        DEFAULT_SERVICES,
        DEEPSEEK_THINKING_FIELDS,
        PDF2ZH_NEXT_SERVICE_ALIASES,
        REASONING_EFFORT_VALUES,
        PDF2ZH_NEXT_EXTRA_FIELDS,
        RELAY_KEYS,
        PDF2ZH_NEXT_BUILTIN_SERVICES,
        UI_TEXT,
        DEPRECATED_DEEPSEEK_MODELS,
    };
})();
