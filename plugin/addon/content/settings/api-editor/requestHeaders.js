/* eslint-disable no-restricted-globals */
/* global document, window, Event */

(() => {
    "use strict";

    const HEADER_SUGGESTIONS = [
        "Content-Type",
        "Accept",
        "Authorization",
        "User-Agent",
        "OpenAI-Organization",
        "OpenAI-Project",
        "X-Client-Request-Id",
        "x-api-key",
        "anthropic-version",
        "anthropic-beta",
        "anthropic-workspace-id",
        "anthropic-user-profile-id",
        "HTTP-Referer",
        "X-OpenRouter-Title",
        "X-OpenRouter-Categories",
        "X-Title",
    ];
    const TEXT = {
        zh: {
            auth: "认证",
            autoAuth: "自动",
            bearer: "Bearer",
            apiKey: "x-api-key",
            credential: "<使用上方 API Key / Token>",
            key: "Key",
            value: "Value",
            remove: "删除",
            add: "添加请求头",
            customValue: "输入自定义值",
            chooseKey: "选择请求头字段",
            chooseValue: "选择请求头值",
            omitHeader: "省略该头（null）",
            emptyValue: "发送空字符串",
        },
        en: {
            auth: "Authentication",
            autoAuth: "Automatic",
            bearer: "Bearer",
            apiKey: "x-api-key",
            credential: "<Use the API Key / Token above>",
            key: "Key",
            value: "Value",
            remove: "Delete",
            add: "Add request header",
            customValue: "Enter a custom value",
            chooseKey: "Choose header field",
            chooseValue: "Choose header value",
            omitHeader: "Omit header (null)",
            emptyValue: "Send an empty string",
        },
    };

    let sourceInput;
    let authSelect;
    let automaticRows;
    let customRows;
    let settingsReader;
    let streamRequest = false;

    function text(key) {
        const language = document.documentElement.lang.toLowerCase();
        return TEXT[language.startsWith("zh") ? "zh" : "en"][key];
    }

    function createElement(tag, attributes = {}, content = "") {
        const element = document.createElementNS(
            "http://www.w3.org/1999/xhtml",
            tag,
        );
        for (const [name, value] of Object.entries(attributes)) {
            element.setAttribute(name, value);
        }
        element.textContent = content;
        return element;
    }

    function createSelect(choices, attributes = {}) {
        const select = createElement("select", attributes);
        for (const [value, label] of choices) {
            select.appendChild(createElement("option", { value }, text(label)));
        }
        return select;
    }

    function automaticHeaders(apiFormat, apiKey, stream, authMode) {
        const headers = {
            "Content-Type": "application/json",
            Accept: stream ? "text/event-stream" : "application/json",
        };
        const authentication =
            authMode === "auto"
                ? apiFormat === "messages"
                    ? "x-api-key"
                    : "bearer"
                : authMode;
        if (authentication === "x-api-key") {
            headers["x-api-key"] = String(apiKey || "");
        } else {
            headers.Authorization = `Bearer ${apiKey || ""}`;
        }
        if (apiFormat === "messages") {
            headers["anthropic-version"] = "2023-06-01";
        }
        return headers;
    }

    function buildRequestHeaders(
        apiFormat,
        apiKey,
        customHeaders,
        stream = false,
        authMode = "auto",
    ) {
        const headers = new Map(
            Object.entries(
                automaticHeaders(apiFormat, apiKey, stream, authMode),
            ).map(([name, value]) => [name.toLowerCase(), [name, value]]),
        );
        for (const [name, value] of Object.entries(customHeaders || {})) {
            if (value === null) {
                headers.delete(name.toLowerCase());
            } else {
                headers.set(name.toLowerCase(), [name, String(value)]);
            }
        }
        return Object.fromEntries(headers.values());
    }

    function readCustomHeaders() {
        const headers = new Map();
        for (const row of customRows.children) {
            const name = row.querySelector(".request-header-key").value.trim();
            if (!name) continue;
            headers.set(name.toLowerCase(), [name, row.headerValue]);
        }
        return Object.fromEntries(headers.values());
    }

    function serializeHeaders() {
        const headers = readCustomHeaders();
        sourceInput.value =
            Object.keys(headers).length > 0 ? JSON.stringify(headers) : "";
        return sourceInput.value;
    }

    function publishHeaders() {
        serializeHeaders();
        refreshAutomaticHeaders();
        sourceInput.dispatchEvent(new Event("input", { bubbles: true }));
    }

    function suggestedHeaderValues(name) {
        switch (name.trim().toLowerCase()) {
            case "content-type":
                return ["application/json"];
            case "accept":
                return streamRequest
                    ? ["text/event-stream", "application/json"]
                    : ["application/json", "text/event-stream"];
            case "anthropic-version":
                return ["2023-06-01"];
            default:
                return [];
        }
    }

    function addHeaderRow(name = "", value = "", useSuggestedValue = false) {
        const row = createElement("div", { class: "request-header-row" });
        const keyCell = createElement("div", { class: "editor-combobox" });
        const keyInput = createElement("input", {
            class: "request-header-key",
            type: "text",
            placeholder: text("key"),
            "aria-label": text("key"),
        });
        keyInput.value = name;
        const keyChoices = createElement("select", {
            "aria-label": text("chooseKey"),
        });
        keyChoices.appendChild(
            createElement("option", { value: "", disabled: "disabled" }, "▼"),
        );
        for (const header of HEADER_SUGGESTIONS) {
            keyChoices.appendChild(
                createElement("option", { value: header }, header),
            );
        }
        keyCell.append(keyInput, keyChoices);
        const valueCell = createElement("div", { class: "editor-combobox" });
        const valueInput = createElement("input", {
            class: "request-header-value",
            type: "text",
            placeholder: text("customValue"),
            "aria-label": text("value"),
        });
        valueInput.value = value === null ? "null" : String(value);
        row.headerValue = value === null ? null : String(value);
        const valueChoices = createElement("select", {
            "aria-label": text("chooseValue"),
        });
        row.refreshValueChoices = () => {
            valueChoices.replaceChildren();
            valueChoices.appendChild(
                createElement(
                    "option",
                    { value: "", disabled: "disabled" },
                    "▼",
                ),
            );
            for (const suggested of suggestedHeaderValues(keyInput.value)) {
                valueChoices.appendChild(
                    createElement("option", { value: suggested }, suggested),
                );
            }
            valueChoices.append(
                createElement(
                    "option",
                    { value: "__header_null__" },
                    text("omitHeader"),
                ),
                createElement(
                    "option",
                    { value: "__header_empty__" },
                    text("emptyValue"),
                ),
            );
            valueChoices.value = "";
        };
        row.refreshValueChoices();
        valueCell.append(valueInput, valueChoices);
        const deleteButton = createElement(
            "button",
            {
                type: "button",
                title: text("remove"),
                "aria-label": text("remove"),
            },
            "×",
        );
        row.append(keyCell, valueCell, deleteButton);
        customRows.appendChild(row);
        keyInput.addEventListener("input", publishHeaders);
        keyInput.addEventListener("change", () => {
            const suggested = suggestedHeaderValues(keyInput.value)[0];
            if (useSuggestedValue && row.headerValue === "" && suggested) {
                row.headerValue = suggested;
                valueInput.value = suggested;
                useSuggestedValue = false;
            }
            publishHeaders();
        });
        keyChoices.addEventListener("change", () => {
            keyInput.value = keyChoices.value;
            keyChoices.value = "";
            keyInput.dispatchEvent(new Event("change", { bubbles: true }));
        });
        valueInput.addEventListener("input", () => {
            row.headerValue = valueInput.value;
            useSuggestedValue = false;
            publishHeaders();
        });
        valueChoices.addEventListener("change", () => {
            const selected = valueChoices.value;
            row.headerValue =
                selected === "__header_null__"
                    ? null
                    : selected === "__header_empty__"
                      ? ""
                      : selected;
            valueInput.value =
                row.headerValue === null ? "null" : row.headerValue;
            useSuggestedValue = false;
            publishHeaders();
        });
        deleteButton.addEventListener("click", () => {
            row.remove();
            publishHeaders();
        });
        return { keyInput, valueInput };
    }

    function refreshAutomaticHeaders({ stream } = {}) {
        const settings = settingsReader();
        streamRequest = Boolean(stream ?? settings.stream ?? streamRequest);
        const defaults = automaticHeaders(
            settings.apiFormat,
            text("credential"),
            streamRequest,
            authSelect.value,
        );
        const overriddenNames = new Set(
            Object.keys(readCustomHeaders()).map((name) => name.toLowerCase()),
        );
        for (const row of customRows.children) row.refreshValueChoices();
        automaticRows.replaceChildren();
        for (const [name, value] of Object.entries(defaults)) {
            if (overriddenNames.has(name.toLowerCase())) continue;
            const row = createElement("div", {
                class: "request-header-row request-header-automatic",
            });
            const keyInput = createElement("input", {
                class: "request-header-key",
                type: "text",
                "aria-label": text("key"),
            });
            keyInput.value = name;
            keyInput.readOnly = true;
            const valueInput = createElement("input", {
                class: "request-header-value",
                type: "text",
                "aria-label": text("value"),
            });
            valueInput.value = value;
            valueInput.readOnly = true;
            row.append(keyInput, valueInput);
            automaticRows.appendChild(row);
        }
    }

    function loadHeaders(value, authMode = "auto") {
        const headers =
            typeof value === "string"
                ? JSON.parse(value.trim() || "{}")
                : value || {};
        customRows.replaceChildren();
        authSelect.value = authMode;
        for (const [name, headerValue] of Object.entries(headers)) {
            addHeaderRow(name, headerValue);
        }
        serializeHeaders();
        refreshAutomaticHeaders();
    }

    function initialize({ container, getSettings, extraData = {} } = {}) {
        sourceInput = document.getElementById("relay-headers");
        sourceInput.hidden = true;
        settingsReader = getSettings;
        const editor = createElement("div", {
            id: "request-headers-editor",
            class: "request-headers-editor",
        });
        const toolbar = createElement("div", {
            class: "request-header-toolbar",
        });
        authSelect = createSelect(
            [
                ["auto", "autoAuth"],
                ["bearer", "bearer"],
                ["x-api-key", "apiKey"],
            ],
            { id: "relay-auth-mode" },
        );
        toolbar.append(
            createElement("label", { for: "relay-auth-mode" }, text("auth")),
            authSelect,
        );
        const columnLabels = createElement("div", {
            class: "request-header-row request-header-columns",
        });
        for (const key of ["key", "value"]) {
            columnLabels.appendChild(createElement("span", {}, text(key)));
        }
        automaticRows = createElement("div", {
            id: "automatic-request-headers",
        });
        customRows = createElement("div", { id: "custom-request-headers" });
        const addButton = createElement(
            "button",
            { type: "button", class: "btn btn-secondary btn-compact" },
            text("add"),
        );
        addButton.addEventListener("click", () => {
            addHeaderRow("", "", true).keyInput.focus();
        });
        editor.append(
            toolbar,
            columnLabels,
            automaticRows,
            customRows,
            addButton,
        );
        if (container) {
            container.appendChild(editor);
        } else {
            sourceInput.parentNode.insertBefore(editor, sourceInput);
        }
        authSelect.addEventListener("change", () => {
            refreshAutomaticHeaders();
            sourceInput.dispatchEvent(new Event("input", { bubbles: true }));
        });
        document
            .getElementById("relay-format")
            .addEventListener("change", () => {
                refreshAutomaticHeaders();
            });
        const body = document.getElementById("relay-body").value.trim();
        streamRequest = Boolean(JSON.parse(body || "{}").stream);
        loadHeaders(
            extraData.zotero_extra_headers ?? sourceInput.value,
            extraData.zotero_auth_mode || "auto",
        );
    }

    window.LlmApiEditorRequestHeaders = {
        initialize,
        loadHeaders,
        serializeHeaders,
        refreshAutomaticHeaders,
        buildRequestHeaders,
        getAuthMode: () => authSelect.value,
        getHeaders: readCustomHeaders,
    };
})();
