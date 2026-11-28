/* eslint-disable no-restricted-globals */
/* global window */

(() => {
    "use strict";

    const BODY_TEMPLATE_FIELD = "zotero_body_template";
    const FIELD_DEFAULTS = {
        temperature: 0,
        top_p: 1,
        max_tokens: 8192,
        max_output_tokens: 8192,
        max_completion_tokens: 8192,
    };
    const FIELD_DEFINITIONS = {
        model: ["string", "模型", "common"],
        messages: ["json", "对话输入", "common"],
        input: ["json", "翻译输入", "common"],
        instructions: ["string", "附加指令", "common"],
        system: ["json", "系统提示词", "common"],
        temperature: ["number", "温度", "common"],
        top_p: ["number", "核采样", "common"],
        top_k: ["number", "Top-K 采样（旧版）", "advanced"],
        frequency_penalty: ["number", "重复次数惩罚", "common"],
        presence_penalty: ["number", "重复出现惩罚", "common"],
        max_completion_tokens: ["number", "输出上限", "common"],
        max_output_tokens: ["number", "输出上限", "common"],
        max_tokens: ["number", "输出上限", "common"],
        stop: ["json", "停止序列", "common"],
        stop_sequences: ["json", "停止序列", "common"],
        stream: ["boolean", "流式返回", "common"],
        stream_options: ["json", "流式选项", "advanced"],
        "stream_options.include_usage": [
            "boolean",
            "流式 token 统计",
            "common",
        ],
        "stream_options.include_obfuscation": [
            "boolean",
            "流式附加数据",
            "advanced",
        ],
        reasoning_effort: [
            "enum",
            "推理强度",
            "common",
            ["none", "minimal", "low", "medium", "high", "xhigh", "max"],
        ],
        reasoning: ["json", "推理配置", "format"],
        "reasoning.effort": [
            "enum",
            "推理强度",
            "common",
            ["none", "minimal", "low", "medium", "high", "xhigh", "max"],
        ],
        "reasoning.summary": [
            "enum",
            "推理摘要",
            "format",
            ["auto", "concise", "detailed"],
        ],
        "reasoning.context": [
            "enum",
            "推理上下文",
            "advanced",
            ["auto", "current_turn", "all_turns"],
        ],
        "reasoning.mode": ["enum", "推理模式", "advanced", ["standard", "pro"]],
        verbosity: [
            "enum",
            "输出详细程度",
            "format",
            ["low", "medium", "high"],
        ],
        response_format: ["json", "输出格式", "format"],
        "response_format.type": [
            "enum",
            "输出格式类型",
            "format",
            ["text", "json_object", "json_schema"],
        ],
        "response_format.json_schema": ["json", "输出 JSON Schema", "format"],
        text: ["json", "文本输出配置", "format"],
        "text.verbosity": [
            "enum",
            "输出详细程度",
            "format",
            ["low", "medium", "high"],
        ],
        "text.format": ["json", "输出格式", "format"],
        thinking: ["json", "Claude 思考配置", "format"],
        "thinking.type": [
            "enum",
            "Claude 思考模式",
            "format",
            ["adaptive", "enabled", "disabled"],
        ],
        "thinking.budget_tokens": ["number", "思考 token 预算", "format"],
        "thinking.display": [
            "enum",
            "思考内容显示",
            "format",
            ["summarized", "omitted"],
        ],
        output_config: ["json", "Claude 输出配置", "format"],
        "output_config.effort": [
            "enum",
            "输出 effort",
            "common",
            ["low", "medium", "high", "xhigh", "max"],
        ],
        "output_config.format": ["json", "输出 JSON Schema", "format"],
        store: ["boolean", "保存响应", "cache"],
        metadata: ["json", "附加元数据", "cache"],
        prompt_cache_key: ["string", "提示词缓存标识", "cache"],
        prompt_cache_retention: [
            "enum",
            "缓存保留策略",
            "cache",
            ["in_memory", "24h"],
        ],
        prompt_cache_options: ["json", "缓存断点与 TTL", "cache"],
        cache_control: ["json", "缓存标记", "cache"],
        "cache_control.type": ["enum", "缓存类型", "cache", ["ephemeral"]],
        "cache_control.ttl": ["enum", "缓存 TTL", "cache", ["5m", "1h"]],
        service_tier: [
            "enum",
            "服务档位",
            "common",
            ["auto", "default", "flex", "scale", "priority", "fast"],
        ],
        speed: ["enum", "推理速度", "common", ["standard", "fast"]],
        truncation: ["enum", "输入截断策略", "common", ["auto", "disabled"]],
        safety_identifier: ["string", "调用用户标识", "advanced"],
        user: ["string", "旧用户标识（已弃用）", "advanced"],
        seed: ["number", "采样种子（已弃用）", "advanced"],
        logit_bias: ["json", "token 采样偏置", "advanced"],
        logprobs: ["boolean", "token 对数概率", "advanced"],
        top_logprobs: ["number", "候选 token 概率数量", "advanced"],
        n: ["number", "候选补全数量", "advanced"],
        tools: ["json", "工具定义", "advanced"],
        tool_choice: ["json", "工具选择", "advanced"],
        parallel_tool_calls: ["boolean", "并行工具调用", "advanced"],
        max_tool_calls: ["number", "工具调用数量上限", "advanced"],
        web_search_options: ["json", "网页搜索配置", "advanced"],
        prediction: ["json", "预测输出配置", "advanced"],
        modalities: ["json", "输出模态", "advanced"],
        audio: ["json", "音频输出配置", "advanced"],
        moderation: ["json", "官方 moderation 配置", "advanced"],
        function_call: ["json", "旧函数调用（已弃用）", "advanced"],
        functions: ["json", "旧函数定义（已弃用）", "advanced"],
        include: ["json", "响应附加内容", "advanced"],
        previous_response_id: ["string", "上一条响应 ID", "advanced"],
        conversation: ["json", "关联会话", "advanced"],
        prompt: ["json", "可复用提示词", "advanced"],
        context_management: ["json", "上下文管理", "advanced"],
        background: ["boolean", "后台执行", "advanced"],
        background_options: ["json", "后台执行选项", "advanced"],
        image: ["json", "请求级图像配置", "advanced"],
        access_programs: ["json", "官方访问计划", "advanced"],
        container: ["json", "执行容器", "advanced"],
        diagnostics: ["json", "请求诊断配置", "advanced"],
        inference_geo: ["string", "推理处理地区", "advanced"],
        provider: ["json", "OpenRouter 服务商路由", "advanced"],
        min_p: ["number", "OpenRouter 最小概率采样", "advanced"],
        top_a: ["number", "OpenRouter Top-A 采样", "advanced"],
        repetition_penalty: ["number", "OpenRouter 重复惩罚", "advanced"],
        include_reasoning: ["boolean", "OpenRouter 推理内容", "advanced"],
    };

    const PROTOCOL_FIELDS = {
        chat: [
            "model",
            "messages",
            "temperature",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "max_completion_tokens",
            "max_tokens",
            "stop",
            "stream",
            "stream_options",
            "stream_options.include_usage",
            "stream_options.include_obfuscation",
            "reasoning_effort",
            "verbosity",
            "response_format",
            "response_format.type",
            "response_format.json_schema",
            "store",
            "metadata",
            "service_tier",
            "prompt_cache_key",
            "prompt_cache_retention",
            "prompt_cache_options",
            "safety_identifier",
            "seed",
            "logit_bias",
            "logprobs",
            "top_logprobs",
            "n",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "web_search_options",
            "prediction",
            "modalities",
            "audio",
            "moderation",
            "user",
            "function_call",
            "functions",
        ],
        responses: [
            "model",
            "input",
            "instructions",
            "max_output_tokens",
            "temperature",
            "top_p",
            "reasoning",
            "reasoning.effort",
            "reasoning.summary",
            "reasoning.context",
            "reasoning.mode",
            "text",
            "text.verbosity",
            "text.format",
            "stream",
            "stream_options",
            "stream_options.include_obfuscation",
            "store",
            "metadata",
            "service_tier",
            "prompt_cache_key",
            "prompt_cache_retention",
            "prompt_cache_options",
            "truncation",
            "include",
            "top_logprobs",
            "safety_identifier",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "max_tool_calls",
            "previous_response_id",
            "conversation",
            "prompt",
            "context_management",
            "background",
            "background_options",
            "image",
            "moderation",
            "access_programs",
            "user",
        ],
        messages: [
            "model",
            "messages",
            "max_tokens",
            "system",
            "stream",
            "stop_sequences",
            "thinking",
            "thinking.type",
            "thinking.budget_tokens",
            "thinking.display",
            "output_config",
            "output_config.effort",
            "output_config.format",
            "cache_control",
            "cache_control.type",
            "cache_control.ttl",
            "metadata",
            "service_tier",
            "speed",
            "container",
            "diagnostics",
            "inference_geo",
            "tool_choice",
            "tools",
            "temperature",
            "top_k",
            "top_p",
        ],
    };

    const EXPANDABLE_FIELDS = new Set([
        "reasoning",
        "text",
        "response_format",
        "output_config",
        "stream_options",
        "thinking",
        "cache_control",
    ]);
    const AUTOMATIC_FIELDS = new Set(["model", "messages", "input"]);
    const EFFORT_PATHS = {
        chat: "reasoning_effort",
        responses: "reasoning.effort",
        messages: "output_config.effort",
    };
    const TEXT = {
        zh: {
            title: "请求体",
            template: "请求体模板",
            standard: "标准",
            minimal: "最少字段",
            stream: "流式",
            common: "常用",
            format: "输出格式",
            cache: "缓存与归属",
            advanced: "高级",
            custom: "自定义字段",
            add: "＋ 添加请求体字段",
            enabled: "发送",
            key: "Key",
            type: "类型",
            value: "Value",
            unset: "未设置",
            automatic: "自动",
            model: "引用上方模型名称",
            input: "由翻译引擎生成",
            managed: "在原“添加参数”中设置",
            managedSource: "原参数",
            minimalHint:
                "最少字段模板暂不发送原参数区的可选请求字段；配置值仍保留。",
            fieldHint:
                "可选字段未设置时省略。布尔 false 和数字 0 会按实际值发送。",
            messagesHint:
                "Messages 2026-10-21 已删除 temperature、top_p、top_k；旧版也需按模型支持填写。",
            advancedHint:
                "高级字段按服务商支持填写；工具、音频和后台任务需要对应结果处理。",
            preview: "请求体预览",
            previewHint: "模型与输入的说明文字仅用于预览，不会保存为请求字段。",
            jsonMode: "JSON 模式",
            string: "字符串",
            number: "数字",
            boolean: "布尔",
            json: "JSON",
            enum: "建议值",
            null: "null",
            remove: "删除字段",
        },
        en: {
            title: "Request body",
            template: "Body template",
            standard: "Standard",
            minimal: "Minimal",
            stream: "Streaming",
            common: "Common",
            format: "Output format",
            cache: "Caching and metadata",
            advanced: "Advanced",
            custom: "Custom field",
            add: "+ Add body field",
            enabled: "Send",
            key: "Key",
            type: "Type",
            value: "Value",
            unset: "Unset",
            automatic: "Automatic",
            model: "Uses the model above",
            input: "Generated by the translation engine",
            managed: "Set in the existing extra parameters",
            managedSource: "Parameters",
            minimalHint:
                "Minimal omits optional engine parameters while keeping their saved values.",
            fieldHint:
                "Unset optional fields are omitted. Boolean false and numeric 0 are sent as entered.",
            messagesHint:
                "Messages 2026-10-21 removed temperature, top_p and top_k; older versions also depend on model support.",
            advancedHint:
                "Use advanced fields as your provider supports. Tools, audio and background jobs need corresponding result handling.",
            preview: "Body preview",
            previewHint:
                "Model and input descriptions appear only in this preview and are never saved as request values.",
            jsonMode: "JSON mode",
            string: "String",
            number: "Number",
            boolean: "Boolean",
            json: "JSON",
            enum: "Suggested value",
            null: "null",
            remove: "Remove field",
        },
    };

    function getFields(apiFormat, apiVersion = "2023-06-01", service = "") {
        const keys = [...PROTOCOL_FIELDS[apiFormat]];
        if (service.toLowerCase() === "openrouter") {
            keys.push(
                "provider",
                "top_k",
                "min_p",
                "top_a",
                "repetition_penalty",
                "include_reasoning",
                "reasoning",
            );
        }
        return [...new Set(keys)]
            .filter(
                (key) =>
                    apiFormat !== "messages" ||
                    apiVersion < "2026-10-21" ||
                    !["temperature", "top_p", "top_k"].includes(key),
            )
            .map((key) => {
                const [type, label, group, values = []] =
                    FIELD_DEFINITIONS[key];
                return {
                    key,
                    type,
                    label,
                    group,
                    values:
                        apiFormat === "messages" && key === "service_tier"
                            ? ["auto", "standard_only"]
                            : values,
                };
            });
    }

    function isObject(value) {
        return (
            value !== null && typeof value === "object" && !Array.isArray(value)
        );
    }

    function setBodyField(body, key, value) {
        const parts = key.split(".");
        let target = body;
        for (const part of parts.slice(0, -1)) {
            target[part] ??= {};
            target = target[part];
        }
        target[parts[parts.length - 1]] = value;
    }

    function mergeBodyFields(body, fields) {
        for (const [key, value] of Object.entries(fields)) {
            if (isObject(value) && isObject(body[key])) {
                mergeBodyFields(body[key], value);
            } else {
                body[key] = value;
            }
        }
        return body;
    }

    function bodyEntries(body) {
        const entries = [];
        for (const [key, value] of Object.entries(body)) {
            if (
                EXPANDABLE_FIELDS.has(key) &&
                isObject(value) &&
                Object.keys(value).length
            ) {
                for (const [childKey, childValue] of Object.entries(value)) {
                    entries.push([`${key}.${childKey}`, childValue]);
                }
            } else {
                entries.push([key, value]);
            }
        }
        return entries;
    }

    function valueType(value, definition) {
        if (value === null) return "null";
        if (typeof value === "boolean") return "boolean";
        if (typeof value === "number") return "number";
        if (typeof value === "object") return "json";
        return definition?.type === "enum" ? "enum" : "string";
    }

    function create({
        container,
        apiFormat = "chat",
        apiVersion = "2023-06-01",
        service = "",
        managedParameters = {},
        language = "zh",
        onChange = () => {},
    }) {
        const document = container.ownerDocument;
        const text = TEXT[language];
        managedParameters = { ...managedParameters };
        let template = "standard";
        let rows = [];
        const savedBodies = {};

        function element(tag, className, content) {
            const node = document.createElement(tag);
            if (className) node.className = className;
            if (content !== undefined) node.textContent = content;
            return node;
        }

        function option(select, value, label) {
            const node = element("option", "", label);
            node.value = value;
            select.appendChild(node);
        }

        const root = element("section", "llm-request-body-editor");
        const toolbar = element("div", "body-toolbar");
        const templateSelect = element("select", "body-template");
        templateSelect.id = `body-template-${create.nextListId++}`;
        templateSelect.setAttribute("aria-label", text.template);
        for (const name of ["standard", "minimal", "stream"]) {
            option(templateSelect, name, text[name]);
        }
        const templateLabel = element("label", "", text.template);
        templateLabel.htmlFor = templateSelect.id;
        toolbar.append(templateLabel, templateSelect);
        root.appendChild(toolbar);

        const table = element("table", "body-table");
        const header = element("thead");
        const headerRow = element("tr");
        for (const [className, label] of [
            ["body-key-column", text.key],
            ["body-value-column", text.value],
            ["body-delete-column", ""],
        ]) {
            headerRow.appendChild(element("th", className, label));
        }
        header.appendChild(headerRow);
        const editableRows = element("tbody", "body-rows");
        table.append(header, editableRows);
        root.appendChild(table);

        const suggestions = element("datalist");
        suggestions.id = `body-keys-${create.nextListId++}`;
        root.appendChild(suggestions);
        const addToolbar = element("div", "body-toolbar");
        const addButton = element("button", "body-add", text.add);
        addButton.type = "button";
        addToolbar.appendChild(addButton);
        root.appendChild(addToolbar);
        container.appendChild(root);

        function definitionFor(key) {
            return getFields(apiFormat, apiVersion, service).find(
                (field) => field.key === key,
            );
        }

        function refreshSuggestions() {
            suggestions.replaceChildren();
            for (const field of getFields(apiFormat, apiVersion, service)) {
                option(
                    suggestions,
                    field.key,
                    language === "zh" ? field.label : field.key,
                );
            }
        }

        function readRowValue(row) {
            const raw = row.value.value;
            if (row.kind === "number") return row.value.valueAsNumber;
            if (["boolean", "json", "null"].includes(row.kind)) {
                return JSON.parse(raw);
            }
            if (row.kind === "custom") {
                try {
                    return JSON.parse(raw);
                } catch {
                    return raw;
                }
            }
            return raw;
        }

        function collect() {
            const extraBody = {};
            for (const row of rows) {
                const key = row.key.value.trim();
                if (
                    !key ||
                    (["number", "boolean", "json", "null"].includes(row.kind) &&
                        row.value.value === "")
                )
                    continue;
                setBodyField(extraBody, key, readRowValue(row));
            }
            return { template, extraBody };
        }

        function notify(emitChange = true) {
            if (!emitChange) return;
            let state;
            try {
                state = collect();
            } catch {
                return;
            }
            onChange({
                ...state,
                managedParameters: { ...managedParameters },
            });
        }

        function renderValue(row, value, definition) {
            row.valueCell.replaceChildren();
            let input;
            if (row.kind === "boolean") {
                input = element("select");
                option(input, "", text.unset);
                option(input, "false", "false");
                option(input, "true", "true");
                input.value = String(value ?? "");
            } else if (row.kind === "json") {
                input = element("textarea");
                input.rows = 2;
                input.spellcheck = false;
                input.value =
                    value === undefined ? "" : JSON.stringify(value, null, 2);
            } else {
                input = element("input");
                input.type = row.kind === "number" ? "number" : "text";
                if (row.kind === "number") input.step = "any";
                input.value =
                    row.kind === "null" ? "null" : String(value ?? "");
                if (row.kind === "enum" && definition) {
                    const values = element("datalist");
                    values.id = `body-values-${create.nextListId++}`;
                    for (const suggested of definition.values)
                        option(values, suggested, suggested);
                    row.valueCell.appendChild(values);
                    input.setAttribute("list", values.id);
                }
            }
            input.className = "body-value";
            input.placeholder = text.unset;
            input.setAttribute("aria-label", `${row.key.value} ${text.value}`);
            input.addEventListener(
                row.kind === "boolean" ? "change" : "input",
                () => {
                    row.templateField = false;
                    row.newField = false;
                    notify();
                },
            );
            row.value = input;
            row.valueCell.appendChild(input);
        }

        function removeRow(row) {
            rows = rows.filter((candidate) => candidate !== row);
            row.element.remove();
        }

        function addRow(key = "", value, templateField = false) {
            const definition = definitionFor(key);
            const row = {
                element: element("tr", "body-row"),
                key: element("input", "body-key"),
                valueCell: element("td", "body-value-cell"),
                kind:
                    value === undefined
                        ? definition?.type || "custom"
                        : valueType(value, definition),
                templateField,
                newField: value === undefined,
            };
            row.key.type = "text";
            row.key.value = key;
            row.key.placeholder = text.key;
            row.key.title =
                language === "zh" ? definition?.label || text.custom : key;
            row.key.setAttribute("list", suggestions.id);
            row.key.setAttribute("aria-label", text.key);
            const keyCell = element("td", "body-key-cell");
            keyCell.appendChild(row.key);
            const deleteCell = element("td", "body-delete-column");
            const deleteButton = element("button", "body-delete", "×");
            deleteButton.type = "button";
            deleteButton.title = text.remove;
            deleteButton.setAttribute("aria-label", text.remove);
            deleteButton.addEventListener("click", () => {
                removeRow(row);
                notify();
            });
            deleteCell.appendChild(deleteButton);
            row.element.append(keyCell, row.valueCell, deleteCell);
            editableRows.appendChild(row.element);
            rows.push(row);
            renderValue(row, value, definition);
            row.key.addEventListener("input", () => {
                row.templateField = false;
                const newDefinition = definitionFor(row.key.value.trim());
                if (row.newField) {
                    row.kind = newDefinition?.type || "custom";
                    const defaultValue =
                        FIELD_DEFAULTS[row.key.value.trim()] ??
                        (row.kind === "boolean"
                            ? false
                            : row.kind === "number"
                              ? 0
                              : undefined);
                    renderValue(row, defaultValue, newDefinition);
                }
                row.key.title =
                    language === "zh"
                        ? newDefinition?.label || text.custom
                        : row.key.value;
                row.value.setAttribute(
                    "aria-label",
                    `${row.key.value} ${text.value}`,
                );
                notify();
            });
            return row;
        }

        function addTemplateRows() {
            const fields = apiFormat === "messages" ? { max_tokens: 8192 } : {};
            if (template !== "minimal") {
                if (apiFormat === "responses") fields.store = false;
                fields.stream = template === "stream";
            }
            const configured = new Set(rows.map((row) => row.key.value.trim()));
            for (const [key, value] of Object.entries(fields)) {
                if (!configured.has(key)) addRow(key, value, true);
            }
        }

        function load(
            {
                template: selectedTemplate = "standard",
                extraBody = {},
                templateFields = [],
            } = {},
            emitChange = true,
        ) {
            template = selectedTemplate;
            templateSelect.value = template;
            rows = [];
            editableRows.replaceChildren();
            const body =
                typeof extraBody === "string"
                    ? JSON.parse(extraBody || "{}")
                    : extraBody;
            for (const [key, value] of bodyEntries(body)) {
                addRow(key, value, templateFields.includes(key));
            }
            addTemplateRows();
            refreshSuggestions();
            notify(emitChange);
        }

        function saveCurrentBody() {
            savedBodies[apiFormat] = {
                ...collect(),
                templateFields: rows
                    .filter((row) => row.templateField)
                    .map((row) => row.key.value.trim()),
            };
        }

        function setApiFormat(format, version = apiVersion) {
            apiVersion = version;
            if (format !== apiFormat) {
                saveCurrentBody();
                apiFormat = format;
                load(savedBodies[format] || { template, extraBody: {} });
            } else {
                refreshSuggestions();
            }
        }

        function setManagedParameters(parameters) {
            managedParameters = { ...parameters };
        }

        function setService(serviceName) {
            service = serviceName;
            refreshSuggestions();
        }

        templateSelect.addEventListener("change", () => {
            for (const row of [...rows]) {
                if (row.templateField || row.key.value.trim() === "stream")
                    removeRow(row);
            }
            template = templateSelect.value;
            addTemplateRows();
            notify();
        });
        addButton.addEventListener("click", () => {
            const row = addRow();
            row.key.focus();
        });

        load({}, false);
        return {
            load,
            setApiFormat,
            setManagedParameters,
            setService,
            collect,
            getManagedParameters: () => ({ ...managedParameters }),
            element: root,
        };
    }
    create.nextListId = 1;

    window.LLMRequestBodyEditor = { BODY_TEMPLATE_FIELD, getFields, create };
})();
