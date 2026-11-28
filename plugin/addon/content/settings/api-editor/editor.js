/* eslint-disable no-restricted-globals */
/* global window, document, Components, ChromeUtils, navigator, alert, confirm, fetch, setTimeout, Event */
(() => {
    "use strict";
    const {
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
    } = window.LlmApiEditorPresets;
    let mergedServices = {};
    let currentData = {};
    let isEditMode = false;
    let selectedBuiltinService = "";
    const HISTORY_PREF_KEY = "extensions.pdf2zh.llm.history";
    function isCustomRelayService(serviceKey) {
        const key = String(serviceKey || "").trim();
        if (!key) return false;
        const canonical = PDF2ZH_NEXT_SERVICE_ALIASES[key] || key;
        return (
            !PDF2ZH_NEXT_EXTRA_FIELDS[canonical] &&
            !PDF2ZH_NEXT_BUILTIN_SERVICES.includes(canonical)
        );
    }
    // 接口类型/请求头对 OpenAI、OpenAI-Liked 和自定义服务可用。
    function supportsRelayFields(serviceKey) {
        const key = String(serviceKey || "").trim();
        const canonical = PDF2ZH_NEXT_SERVICE_ALIASES[key] || key;
        return (
            canonical === "openai" ||
            canonical === "openaicompatible" ||
            isCustomRelayService(key)
        );
    }
    let requestHeadersEditor, requestBodyEditor, parametersEditor;

    function getManagedRequestParameters() {
        const values = parametersEditor.serializeParameters();
        const canonical =
            PDF2ZH_NEXT_SERVICE_ALIASES[getCurrentServiceKey()] ||
            getCurrentServiceKey();
        const prefix = canonical === "openai" ? "openai" : "openai_compatible";
        const setting = (name) => values[prefix + "_" + name];
        const flag = (name, fallback) =>
            setting(name) === undefined
                ? fallback
                : setting(name) === true || setting(name) === "true";
        return {
            model: document.getElementById("model").value,
            temperature:
                setting("temperature") === undefined
                    ? undefined
                    : Number(setting("temperature")),
            reasoning_effort: setting("reasoning_effort"),
            send_temperature: flag(
                canonical === "openai" ? "send_temprature" : "send_temperature",
                true,
            ),
            send_reasoning_effort: flag("send_reasoning_effort", true),
            enable_json_mode: flag("enable_json_mode", false),
        };
    }

    function refreshRequestBody() {
        const headers = requestHeadersEditor.getHeaders();
        const version =
            Object.entries(headers).find(
                ([name]) => name.toLowerCase() === "anthropic-version",
            )?.[1] || "2023-06-01";
        requestBodyEditor.setApiFormat(
            document.getElementById("relay-format").value,
            version,
        );
        requestBodyEditor.setManagedParameters(getManagedRequestParameters());
        requestBodyEditor.setService(getCurrentServiceKey());
    }

    function updateRequestEditorMode() {
        const editable = supportsRelayFields(getCurrentServiceKey());
        document.getElementById("api-format-group").hidden = !editable;
        document.getElementById("relay-format").disabled = !editable;
        document.getElementById("request-headers-fields").disabled = !editable;
        document.getElementById("request-body-container").hidden = !editable;
        const note = document.getElementById("native-request-settings-note");
        note.hidden = editable;
        note.textContent = t("nativeRequestSettings");
    }

    function initializeRequestEditors() {
        parametersEditor = window.LlmApiEditorParameters;
        parametersEditor.initialize({
            container: document.getElementById("extra-fields-container"),
            getService: getCurrentServiceKey,
            isCustomService: isCustomRelayService,
            text: t,
            onChange: refreshRequestBody,
            language: uiLanguage,
        });
        requestHeadersEditor = window.LlmApiEditorRequestHeaders;
        requestHeadersEditor.initialize({
            container: document.getElementById("request-headers-container"),
            getSettings: () => ({
                apiFormat: document.getElementById("relay-format").value,
                apiKey: document.getElementById("apiKey").value,
                service: getCurrentServiceKey(),
            }),
        });
        requestBodyEditor = window.LLMRequestBodyEditor.create({
            container: document.getElementById("request-body-container"),
            apiFormat: "chat",
            language: uiLanguage,
            onChange: ({ template, extraBody }) => {
                document.getElementById("relay-body").value =
                    JSON.stringify(extraBody);
                requestHeadersEditor.refreshAutomaticHeaders({
                    stream: extraBody.stream ?? template === "stream",
                });
            },
        });
        for (const id of [
            "relay-format",
            "relay-headers",
            "model",
            "apiUrl",
            "apiKey",
            "extra-fields-container",
        ]) {
            document
                .getElementById(id)
                .addEventListener("input", refreshRequestBody);
            document
                .getElementById(id)
                .addEventListener("change", refreshRequestBody);
        }
        document
            .getElementById("extra-fields-container")
            .addEventListener("click", refreshRequestBody);
    }

    function loadRelayFields(extraData = {}) {
        document.getElementById("relay-format").value =
            extraData.zotero_api_format || "chat";
        requestHeadersEditor.loadHeaders(
            extraData.zotero_extra_headers,
            extraData.zotero_auth_mode || "auto",
        );
        requestBodyEditor.setApiFormat(
            document.getElementById("relay-format").value,
        );
        requestBodyEditor.load({
            template: extraData.zotero_body_template || "standard",
            extraBody: extraData.zotero_extra_body || {},
        });
        refreshRequestBody();
    }

    function collectRelayFields(serviceKey) {
        if (!supportsRelayFields(serviceKey)) {
            const saved = currentData.extraData || {};
            return Object.fromEntries(
                RELAY_KEYS.filter((key) => key in saved).map((key) => [
                    key,
                    saved[key],
                ]),
            );
        }
        const body = requestBodyEditor.collect();
        return {
            zotero_api_format: document.getElementById("relay-format").value,
            zotero_auth_mode: requestHeadersEditor.getAuthMode(),
            zotero_body_template: body.template,
            zotero_extra_headers:
                requestHeadersEditor.serializeHeaders() || "{}",
            zotero_extra_body: JSON.stringify(body.extraBody),
        };
    }

    function initializeModelCatalog() {
        window.LlmApiEditorModels.initialize({
            http: Zotero.HTTP,
            actionsContainer: document.getElementById("model-actions"),
            statusElement: document.getElementById("fetch-models-status"),
            getCurrentConfig: () => ({
                service: getCurrentServiceKey(),
                model: document.getElementById("model").value,
                apiUrl: document.getElementById("apiUrl").value.trim(),
                apiKey: document.getElementById("apiKey").value.trim(),
                extraData: {
                    zotero_api_format:
                        document.getElementById("relay-format").value,
                    zotero_auth_mode: requestHeadersEditor.getAuthMode(),
                    zotero_extra_headers: requestHeadersEditor.getHeaders(),
                },
            }),
            getModel: () => document.getElementById("model").value,
            updateModels: (service, models, currentModel) => {
                const candidates =
                    service === "deepseek"
                        ? models.filter(
                              (model) => !DEPRECATED_DEEPSEEK_MODELS.has(model),
                          )
                        : models;
                mergedServices[service] = {
                    ...(mergedServices[service] || { name: service }),
                    models: [
                        ...new Set([
                            ...(mergedServices[service]?.models || []),
                            ...candidates,
                        ]),
                    ],
                };
                if (service === getCurrentServiceKey()) {
                    document.getElementById("model").value = currentModel;
                    updateModelOptions(service);
                }
            },
            t: t,
        });
    }

    let Services = globalThis.Services;
    let Zotero = globalThis.Zotero;

    let uiLanguage = "en";
    function getUiLanguage() {
        const locale =
            Zotero?.locale ||
            Services?.locale?.appLocaleAsBCP47 ||
            navigator.language ||
            "en-US";
        return String(locale).toLowerCase().startsWith("zh") ? "zh" : "en";
    }

    function t(key, ...args) {
        const value = UI_TEXT[uiLanguage][key] ?? UI_TEXT.en[key] ?? key;
        return typeof value === "function" ? value(...args) : value;
    }

    function applyLocalization() {
        uiLanguage = getUiLanguage();
        document.documentElement.lang = uiLanguage === "zh" ? "zh-CN" : "en-US";
        document.title = t("windowTitle");
        for (const [id, key] of Object.entries({
            "label-service-name": "serviceName",
            "label-api-key": "apiKey",
            "label-base-url": "baseUrl",
            "label-api-format": "relayFormat",
            "label-model": "modelName",
            "label-relay-headers": "relayHeaders",
            "label-relay-body": "relayBody",
            "cancel-btn": "cancel",
            "save-btn": "saveAndUse",
        })) {
            document.getElementById(id).textContent = t(key);
        }
        const formatLabels = {
            chat: "relayFormatChat",
            responses: "relayFormatResponses",
            messages: "relayFormatMessages",
        };
        for (const option of document.getElementById("relay-format").options) {
            option.textContent = t(formatLabels[option.value]);
        }
        document.getElementById("service").placeholder =
            t("servicePlaceholder");
        document.getElementById("model").placeholder = t("modelPlaceholder");
    }

    function sanitizeDeepSeekHistory(userHistory) {
        const deepseekHistory = userHistory && userHistory.deepseek;
        if (!deepseekHistory || !Array.isArray(deepseekHistory.models)) {
            return userHistory;
        }
        const filtered = deepseekHistory.models.filter(
            (model) => !DEPRECATED_DEEPSEEK_MODELS.has(model),
        );
        if (filtered.length !== deepseekHistory.models.length) {
            deepseekHistory.models = filtered;
            safeSetStorage(userHistory);
        }
        return userHistory;
    }

    function initialize() {
        initGlobals();
        loadAllData();
        applyLocalization();
        initializeRequestEditors();
        initializeForm();
        initializeModelCatalog();
        bindEvents();
        migrateLegacyDeepSeekModel();
        localizeDeepSeekSelectLabels();
        window.arguments?.[0]?._initPromise?.resolve();
    }

    function initGlobals() {
        if (typeof Services === "undefined") {
            try {
                Services = Components.utils.import(
                    "resource://gre/modules/Services.jsm",
                ).Services;
            } catch (e) {
                try {
                    const { Services: S } = ChromeUtils.import(
                        "resource://gre/modules/Services.jsm",
                    );
                    Services = S;
                } catch (e2) {
                    // Hosts may already provide Zotero without exposing Services.
                }
            }
        }
        try {
            let win = Services.wm.getMostRecentWindow("navigator:browser");
            Zotero = win.Zotero;
        } catch (e) {
            // Keep the host-provided Zotero object when no main window is available.
        }
    }

    function safeGetStorage() {
        try {
            if (Zotero && Zotero.Prefs) {
                const val = Zotero.Prefs.get(HISTORY_PREF_KEY);
                if (val) return JSON.parse(val);
            }
        } catch (e) {
            // Invalid suggestion history must not prevent opening saved configurations.
        }
        return {};
    }

    function safeSetStorage(data) {
        try {
            if (Zotero && Zotero.Prefs) {
                Zotero.Prefs.set(HISTORY_PREF_KEY, JSON.stringify(data));
            }
        } catch (e) {
            // Suggestion history is optional; configuration persistence is handled by onSave.
        }
    }

    // 使用主设置目录，补充当前配置和历史中的模型、URL。
    function loadAllData() {
        const args = window.arguments[0];
        const userHistory = sanitizeDeepSeekHistory(safeGetStorage());
        mergedServices = Object.fromEntries(
            args.serviceCatalog.map(({ value, label }) => {
                const defaults = DEFAULT_SERVICES[value] || {};
                const history = userHistory[value] || {};
                const configurations = args.llmApiConfigs.filter(
                    (configuration) => configuration.service === value,
                );
                return [
                    value,
                    {
                        name: label,
                        models: [
                            ...new Set(
                                [
                                    ...configurations.map(
                                        (configuration) => configuration.model,
                                    ),
                                    ...(history.models || []),
                                    ...(defaults.models || []),
                                ].filter(Boolean),
                            ),
                        ],
                        urls: [
                            ...new Set(
                                [
                                    ...configurations.map(
                                        (configuration) => configuration.apiUrl,
                                    ),
                                    ...(history.urls || []),
                                    ...(defaults.urls || []),
                                ].filter(Boolean),
                            ),
                        ],
                    },
                ];
            }),
        );
    }

    // 保存历史 (Key, Model, URL)
    function saveUserHistory(service, model, url, apiKey) {
        if (!service) return;
        const userHistory = safeGetStorage();
        if (!userHistory[service])
            userHistory[service] = {
                name: service,
                models: [],
                urls: [],
                apiKeys: [],
            };

        const saveItem = (prop, value, defaultList) => {
            if (value && (!defaultList || !defaultList.includes(value))) {
                if (!userHistory[service][prop])
                    userHistory[service][prop] = [];
                // 避免重复，如果已存在先移除再放到头部（最近使用）
                userHistory[service][prop] = userHistory[service][prop].filter(
                    (v) => v !== value,
                );
                userHistory[service][prop].unshift(value);
            }
        };

        const defModels =
            (DEFAULT_SERVICES[service] && DEFAULT_SERVICES[service].models) ||
            [];
        saveItem(
            "models",
            service === "deepseek" && DEPRECATED_DEEPSEEK_MODELS.has(model)
                ? ""
                : model,
            defModels,
        );

        const defUrls =
            (DEFAULT_SERVICES[service] && DEFAULT_SERVICES[service].urls) || [];
        saveItem("urls", url, defUrls);

        // API Key 没有默认列表，直接存
        saveItem("apiKeys", apiKey, []);

        safeSetStorage(userHistory);
        loadAllData();
    }

    function getCurrentServiceKey() {
        return (
            selectedBuiltinService ||
            document.getElementById("service").value.trim()
        );
    }

    function setServiceProvider(service, followDefaultUrl = true) {
        const previousService = getCurrentServiceKey();
        const builtin = service && !isCustomRelayService(service);
        const urlInput = document.getElementById("apiUrl");
        if (
            followDefaultUrl &&
            builtin &&
            (!urlInput.value ||
                urlInput.value === DEFAULT_SERVICES[previousService]?.urls?.[0])
        ) {
            urlInput.value = DEFAULT_SERVICES[service]?.urls?.[0] || "";
        }

        selectedBuiltinService = builtin ? service : "";
        const input = document.getElementById("service");
        input.readOnly = Boolean(builtin);
        input.value = builtin
            ? mergedServices[service]?.name || service
            : service;
        input.placeholder = t(
            builtin ? "servicePlaceholder" : "customServicePlaceholder",
        );
        updateModelOptions(service);
        updateUrlSelectOptions(service);
    }

    function updateSuggestions(listId, values, labels = {}) {
        const list = document.getElementById(listId);
        list.replaceChildren();
        const arrow = document.createElement("option");
        arrow.value = "";
        arrow.textContent = "▼";
        list.appendChild(arrow);
        if (listId === "service-options") {
            const customService = document.createElement("option");
            customService.value = CUSTOM_SERVICE_OPTION;
            customService.textContent = t("customServiceOption");
            list.appendChild(customService);
        }
        for (const value of new Set(values)) {
            const option = document.createElement("option");
            option.value = value;
            option.textContent = labels[value] || value;
            list.appendChild(option);
        }
        list.value = "";
    }

    function populateServiceOptions() {
        updateSuggestions(
            "service-options",
            Object.keys(mergedServices),
            Object.fromEntries(
                Object.entries(mergedServices).map(([name, service]) => [
                    name,
                    service.name,
                ]),
            ),
        );
    }

    function updateModelOptions(service) {
        updateSuggestions(
            "model-options",
            mergedServices[service]?.models || [],
        );
    }

    function updateUrlSelectOptions(service) {
        updateSuggestions("url-options", mergedServices[service]?.urls || []);
    }

    function bindInputSelectValue(value, type) {
        document.getElementById(type).value = value;
    }

    function initializeForm() {
        const args = window.arguments[0];
        currentData = args.data || {};
        isEditMode = args.isEdit || false;
        document.getElementById("dialog-title").textContent = t(
            isEditMode ? "editTitle" : "addTitle",
        );
        populateServiceOptions();
        for (const id of ["apiKey", "apiUrl", "model"]) {
            document.getElementById(id).value = currentData[id] || "";
        }
        setServiceProvider(currentData.service || "", !isEditMode);
        const service = getCurrentServiceKey();
        parametersEditor.loadParameters(currentData.extraData || {});
        loadRelayFields(currentData.extraData);
        parametersEditor.refreshForService(service);
        updateRequestEditorMode();
    }

    function bindEvents() {
        document
            .getElementById("save-btn")
            .addEventListener("click", () => saveLLMApi(true));
        document
            .getElementById("cancel-btn")
            .addEventListener("click", () => window.close());
        for (const [selectId, inputId] of [
            ["service-options", "service"],
            ["model-options", "model"],
            ["url-options", "apiUrl"],
        ]) {
            const select = document.getElementById(selectId);
            const input = document.getElementById(inputId);
            select.addEventListener("change", () => {
                const selectedValue = select.value;
                if (inputId === "service") {
                    setServiceProvider(
                        selectedValue === CUSTOM_SERVICE_OPTION
                            ? ""
                            : selectedValue,
                    );
                    if (selectedValue === CUSTOM_SERVICE_OPTION) input.focus();
                } else {
                    input.value = selectedValue;
                }
                input.dispatchEvent(new Event("input", { bubbles: true }));
                input.dispatchEvent(new Event("change", { bubbles: true }));
                select.value = "";
            });
        }
        document.getElementById("service").addEventListener("input", () => {
            const service = getCurrentServiceKey();
            updateModelOptions(service);
            updateUrlSelectOptions(service);
            refreshRequestBody();
        });
        document.getElementById("service").addEventListener("change", () => {
            const service = getCurrentServiceKey();
            parametersEditor.refreshForService(service);
            requestHeadersEditor.refreshAutomaticHeaders();
            updateRequestEditorMode();
        });
    }

    // Server 版本缓存: 打开编辑器时探测一次(失败按旧版处理, fail-closed)。
    let cachedServerVersion = null;
    async function probeServerVersion() {
        try {
            const serverUrl = String(
                document.getElementById("new_serverip")?.value ||
                    (window.arguments?.[0]?.serverUrl ?? ""),
            )
                .trim()
                .replace(/\/+$/, "");
            if (!serverUrl) return;
            const health = await fetch(serverUrl + "/health", {
                cache: "no-store",
            });
            if (!health.ok) return;
            const payload = await health.json();
            cachedServerVersion = String(payload.version || "");
        } catch {
            cachedServerVersion = null;
        }
    }
    probeServerVersion();

    function serverSupportsFlashHook() {
        // 4.1.9 起带 DeepSeek flash 思考控制 hook; 缺版本号/不可达
        // 一律按旧版处理(宁拦勿烧)。
        const match = /^(\d+)\.(\d+)(?:\.(\d+))?/.exec(
            cachedServerVersion || "",
        );
        if (!match) return false;
        // 版本三段完整比较: >= 4.1.9 即带 flash hook。
        const version = [
            Number(match[1]),
            Number(match[2]),
            Number(match[3] || 0),
        ];
        const minimum = [4, 1, 9];
        for (let i = 0; i < 3; i++) {
            if (version[i] !== minimum[i]) {
                return version[i] > minimum[i];
            }
        }
        return true; // 完全相等 = 支持
    }

    function showSaveError(message, fieldId) {
        const status = document.getElementById("editor-save-status");
        status.textContent = message;
        status.style.color = "#b42318";
        if (fieldId) document.getElementById(fieldId).focus();
    }

    function saveLLMApi(useForTranslation = false) {
        const extraDataObject = parametersEditor.serializeParameters();

        const serviceName = getCurrentServiceKey();
        let modelName = document.getElementById("model").value.trim();
        const apiKey = document.getElementById("apiKey").value.trim();
        const apiUrl = document.getElementById("apiUrl").value.trim();
        const activateConfiguration =
            useForTranslation || Boolean(currentData.activate);

        document.getElementById("editor-save-status").textContent = "";
        try {
            Object.assign(extraDataObject, collectRelayFields(serviceName));
        } catch (error) {
            showSaveError(error.message);
            return;
        }

        if (
            serviceName === "deepseek" &&
            DEPRECATED_DEEPSEEK_MODELS.has(modelName)
        ) {
            alert(t("deprecatedDeepSeekModel"));
            return;
        }

        // 保留旧 Server 的 DeepSeek 模型名适配。
        if (
            serviceName === "deepseek" &&
            modelName &&
            /^deepseek-/i.test(modelName) &&
            !/^deepseek-v4-/i.test(modelName)
        ) {
            // deepseek-flash 本名: server >= 4.1.9 有 hook 放行;
            // 旧 server 会丢思考参数, 弹窗自动改 v4-flash。
            if (modelName.toLowerCase() === "deepseek-flash") {
                if (serverSupportsFlashHook()) {
                    // 当前 server 支持 hook, flash 合法, 直接保存
                } else if (confirm(t("deepseekThinkingCompatWarning"))) {
                    modelName = "deepseek-v4-flash";
                    document.getElementById("model").value = modelName;
                } else {
                    return;
                }
            } else {
                // 其他写法无法安全保证思考关闭, 提示后返回修改。
                alert(t("deepseekNonFlashSpellingAlert"));
                return;
            }
        }
        if (serviceName === "deepseek") {
            const mode = extraDataObject.deepseek_thinking_mode;
            const FLASH_EFFORTS = [
                "minimal",
                "low",
                "medium",
                "high",
                "xhigh",
                "max",
                "ultra",
            ];
            if (mode !== "enabled") {
                extraDataObject.deepseek_thinking_mode = "disabled";
                delete extraDataObject.deepseek_reasoning_effort;
            } else if (
                !FLASH_EFFORTS.includes(
                    extraDataObject.deepseek_reasoning_effort,
                )
            ) {
                extraDataObject.deepseek_reasoning_effort = "high";
            }
        }

        const formData = {
            key: currentData.key || "",
            service: serviceName,
            model: modelName,
            apiKey,
            apiUrl,
            activate: activateConfiguration,
            extraData: extraDataObject,
        };
        if (window.arguments && window.arguments[0]) {
            const args = window.arguments[0];
            if (typeof args.onSave === "function") {
                try {
                    const result = args.onSave(formData, useForTranslation);
                    if (!result || !result.success) {
                        showSaveError(result?.message || t("saveFailed"));
                        return;
                    }
                } catch {
                    showSaveError(t("saveFailed"));
                    return;
                }
            }
            args.result = {
                success: true,
                data: formData,
                useForTranslation,
                persisted: typeof args.onSave === "function",
                isEdit: isEditMode,
                originalKey: currentData.key,
            };
        }
        saveUserHistory(serviceName, modelName, apiUrl, apiKey);
        window.close();
    }

    function setExtraSelectValue(key, value) {
        const row = parametersEditor.findParameterRow(key);
        const select = row?.querySelector(".extra-value");
        if (select) select.value = value;
    }

    function localizeDeepSeekSelectLabels() {
        const labels = {
            disabled: t("disabled"),
            enabled: t("enabled"),
            high: t("high"),
            max: t("max"),
        };
        for (const key of [
            "deepseek_thinking_mode",
            "deepseek_reasoning_effort",
        ]) {
            const select = parametersEditor
                .findParameterRow(key)
                ?.querySelector(".extra-value");
            if (!select || select.tagName.toLowerCase() !== "select") continue;
            for (const option of select.options) {
                if (labels[option.value])
                    option.textContent = labels[option.value];
            }
        }
    }

    function migrateLegacyDeepSeekModel() {
        const service = getCurrentServiceKey();
        const modelInput = document.getElementById("model");
        if (
            service !== "deepseek" ||
            !DEPRECATED_DEEPSEEK_MODELS.has(modelInput.value)
        ) {
            return;
        }

        const legacyModel = modelInput.value;
        const explicitMode = Object.prototype.hasOwnProperty.call(
            currentData?.extraData || {},
            "deepseek_thinking_mode",
        );

        bindInputSelectValue("deepseek-v4-flash", "model");
        updateModelOptions("deepseek");

        if (!explicitMode) {
            if (legacyModel === "deepseek-reasoner") {
                setExtraSelectValue("deepseek_thinking_mode", "enabled");
                setExtraSelectValue("deepseek_reasoning_effort", "high");
            } else {
                setExtraSelectValue("deepseek_thinking_mode", "disabled");
            }
            parametersEditor.updateReasoningEffort();
        }

        const status = document.getElementById("fetch-models-status");
        if (status) {
            status.textContent =
                legacyModel === "deepseek-reasoner"
                    ? t("legacyReasoner")
                    : t("legacyChat");
        }
    }

    window.LlmApiEditor = {
        initialize,
        save: saveLLMApi,
        getService: getCurrentServiceKey,
    };
    document.addEventListener("DOMContentLoaded", initialize);
})();
