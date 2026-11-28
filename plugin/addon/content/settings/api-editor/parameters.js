/* eslint-disable no-restricted-globals */
/* global window */

(function () {
    const requestSettingKeys = new Set([
        "zotero_api_format",
        "zotero_extra_headers",
        "zotero_extra_body",
        "zotero_auth_mode",
        "zotero_body_template",
    ]);
    let container;
    let document,
        uiLanguage,
        t,
        getCurrentServiceKey,
        isCustomRelayService,
        onChange;
    const {
        DEEPSEEK_THINKING_FIELDS,
        PDF2ZH_NEXT_SERVICE_ALIASES,
        PDF2ZH_NEXT_EXTRA_FIELDS,
    } = window.LlmApiEditorPresets;

    function initialize(options) {
        container = options.container;
        document = container.ownerDocument;
        uiLanguage = options.language;
        t = options.text;
        getCurrentServiceKey = options.getService;
        isCustomRelayService = options.isCustomService;
        onChange = options.onChange;
        const chinese = options.language === "zh";
        const toolbar = document.createElement("div");
        toolbar.className = "translation-parameter-toolbar";
        const title = document.createElement("h3");
        title.textContent = chinese ? "翻译参数" : "Translation parameters";
        const addButton = document.createElement("button");
        addButton.type = "button";
        addButton.className = "translation-parameter-add";
        addButton.textContent = chinese
            ? "＋ 添加翻译参数"
            : "+ Add translation parameter";
        addButton.addEventListener("click", () => {
            addExtraFieldRow();
            container
                .querySelector(".extra-field-row:last-child .extra-key")
                .focus();
        });
        toolbar.append(title, addButton);
        container.before(toolbar);
    }

    function loadParameters(extraData) {
        container.replaceChildren();
        for (const [key, value] of Object.entries(extraData || {})) {
            if (requestSettingKeys.has(key)) continue;
            addExtraFieldRow(
                key,
                value !== null && typeof value === "object"
                    ? JSON.stringify(value)
                    : value,
            );
            const row = container.querySelector(".extra-field-row:last-child");
            row.originalParameter = {
                value,
                text: row.querySelector(".extra-value").value,
            };
        }
    }

    function serializeParameters() {
        const parameters = {};
        for (const row of container.querySelectorAll(".extra-field-row")) {
            const key = row.querySelector(".extra-key").value;
            const value = row.querySelector(".extra-value").value;
            if (key && key !== "__custom__" && !requestSettingKeys.has(key)) {
                if (row.originalParameter?.text === value) {
                    parameters[key] = row.originalParameter.value;
                } else if (value !== "") {
                    parameters[key] = value;
                }
            }
        }
        return parameters;
    }

    function refreshForService(serviceKey) {
        syncDeepSeekThinkingFields(serviceKey);
    }

    function findParameterRow(key) {
        return Array.from(container.querySelectorAll(".extra-field-row")).find(
            (row) => row.querySelector(".extra-key").value === key,
        );
    }

    function focusParameter(key) {
        let row = findParameterRow(key);
        if (!row) {
            addExtraFieldRow(key);
            row = findParameterRow(key);
        }
        row.scrollIntoView({ block: "nearest" });
        row.querySelector(".extra-value").focus();
    }

    function getParameterValue(key) {
        return findParameterRow(key)?.querySelector(".extra-value").value ?? "";
    }

    function getSupportedExtraFields(serviceKey) {
        const canonical = PDF2ZH_NEXT_SERVICE_ALIASES[serviceKey] || serviceKey;
        if (isCustomRelayService(serviceKey)) {
            return PDF2ZH_NEXT_EXTRA_FIELDS.openaicompatible;
        }
        return PDF2ZH_NEXT_EXTRA_FIELDS[canonical] || [];
    }

    function extraFieldLabel(field) {
        return uiLanguage === "zh" ? field.zh : field.en;
    }

    function findExtraFieldMeta(key) {
        if (!key) return null;
        const catalog = getSupportedExtraFields(getCurrentServiceKey());
        return catalog.find((field) => field.key === key) || null;
    }

    function usedExtraKeys() {
        return Array.from(document.getElementsByClassName("extra-key"))
            .map((el) => (el.value || "").trim())
            .filter(Boolean);
    }

    function unusedSupportedExtraFields() {
        const used = new Set(usedExtraKeys());
        return getSupportedExtraFields(getCurrentServiceKey()).filter(
            (field) => !used.has(field.key),
        );
    }

    function refreshExtraFieldSuggestions() {
        const catalog = getSupportedExtraFields(getCurrentServiceKey());
        const hint = document.getElementById("extra-fields-hint");
        if (!hint) return;
        if (!catalog.length) {
            hint.textContent = t("extraFieldsHintEmpty");
            return;
        }
        const names = catalog.map((field) => field.key).join(", ");
        hint.textContent = t("extraFieldsHint").replace("{fields}", names);
    }

    function bindCustomKeyInput(input, row) {
        input.addEventListener("input", () => {
            syncExtraValueWidget(row);
            refreshExtraFieldSuggestions();
        });
        input.addEventListener("change", () => {
            syncExtraValueWidget(row);
            refreshExtraFieldSuggestions();
        });
    }

    function replaceKeyWithCustomInput(row) {
        const old = row.querySelector(".extra-key");
        if (!old) return;
        const input = document.createElement("input");
        input.type = "text";
        input.className = "extra-key";
        input.placeholder = t("parameterName");
        bindCustomKeyInput(input, row);
        old.replaceWith(input);
        input.focus();
    }

    function createExtraKeyWidget(row, key) {
        const deepseekField = DEEPSEEK_THINKING_FIELDS[key];
        if (deepseekField) {
            const inputKey = document.createElement("input");
            inputKey.type = "text";
            inputKey.className = "extra-key";
            inputKey.placeholder = t("parameterName");
            inputKey.value = key;
            inputKey.readOnly = true;
            inputKey.title = t(deepseekField.titleKey);
            return inputKey;
        }

        if (key) {
            const inputKey = document.createElement("input");
            inputKey.type = "text";
            inputKey.className = "extra-key";
            inputKey.placeholder = t("parameterName");
            inputKey.value = key;
            bindCustomKeyInput(inputKey, row);
            return inputKey;
        }

        const unused = unusedSupportedExtraFields();
        if (!unused.length) {
            const inputKey = document.createElement("input");
            inputKey.type = "text";
            inputKey.className = "extra-key";
            inputKey.placeholder = t("parameterName");
            bindCustomKeyInput(inputKey, row);
            return inputKey;
        }

        const select = document.createElement("select");
        select.className = "extra-key";
        appendSelectOption(select, "", t("selectExtraField"));
        unused.forEach((field) => {
            appendSelectOption(
                select,
                field.key,
                field.key + " — " + extraFieldLabel(field),
            );
        });
        appendSelectOption(select, "__custom__", t("customExtraField"));
        select.addEventListener("change", () => {
            if (select.value === "__custom__") {
                replaceKeyWithCustomInput(row);
                syncExtraValueWidget(row);
                refreshExtraFieldSuggestions();
                return;
            }
            syncExtraValueWidget(row);
            refreshExtraFieldSuggestions();
        });
        return select;
    }

    function appendSelectOption(select, value, label) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = label;
        select.appendChild(option);
    }

    // 组合框: 可下拉选择预设值, 也可自由输入(字段持续扩充, 不锁死选项)。
    function createComboInput(row, values, current, unsetOption) {
        const input = document.createElement("input");
        input.type = "text";
        input.setAttribute("autocomplete", "off");
        const listId = "combo-dl-" + Math.random().toString(36).slice(2, 9);
        const datalist = document.createElement("datalist");
        datalist.id = listId;
        if (unsetOption) {
            const unset = document.createElement("option");
            unset.value = "";
            unset.label = t("extraFieldUnset");
            datalist.appendChild(unset);
        }
        values.forEach((v) => {
            const option = document.createElement("option");
            option.value = v;
            datalist.appendChild(option);
        });
        row.appendChild(datalist);
        input.setAttribute("list", listId);
        input.value = String(current || "");
        return input;
    }

    function createExtraValueWidget(key, value = "") {
        const deepseekField = DEEPSEEK_THINKING_FIELDS[key];
        if (deepseekField) {
            const row =
                document.getElementById("extra-fields-container") ||
                document.body;
            const current = deepseekField.values.includes(value)
                ? value
                : String(value || "").trim() || deepseekField.defaultValue;
            const input = createComboInput(
                row,
                deepseekField.values,
                current,
                false,
            );
            input.setAttribute("data-extra-type", "deepseek");
            input.title = t(deepseekField.titleKey);
            return input;
        }

        const field = findExtraFieldMeta(key);
        const normalized =
            value === true
                ? "true"
                : value === false
                  ? "false"
                  : String(value ?? "");

        if (field && field.type === "bool") {
            const select = document.createElement("select");
            select.setAttribute("data-extra-type", "bool");
            appendSelectOption(select, "", t("extraFieldUnset"));
            appendSelectOption(select, "true", "true");
            appendSelectOption(select, "false", "false");
            select.value =
                normalized === "true" || normalized === "false"
                    ? normalized
                    : "";
            return select;
        }

        if (field && field.type === "enum") {
            const row =
                document.getElementById("extra-fields-container") ||
                document.body;
            const input = createComboInput(
                row,
                field.values || [],
                normalized,
                true,
            );
            input.setAttribute("data-extra-type", "enum");
            return input;
        }

        const input = document.createElement("input");
        input.type = "text";
        input.setAttribute("data-extra-type", "text");
        input.placeholder = t("parameterValue");
        input.value = normalized;
        return input;
    }

    function syncExtraValueWidget(row) {
        const keyInput = row.querySelector(".extra-key");
        const current = row.querySelector(".extra-value");
        if (!keyInput || !current) return;
        const key = (keyInput.value || "").trim();
        const next = createExtraValueWidget(key, current.value);
        next.className = "extra-value";
        const nextType = next.getAttribute("data-extra-type");
        const currentType = current.getAttribute("data-extra-type");
        if (next.tagName === current.tagName && nextType === currentType) {
            return;
        }
        current.replaceWith(next);
        if (key === "deepseek_thinking_mode") {
            next.addEventListener("change", updateDeepSeekReasoningEffortState);
        }
    }

    function addExtraFieldRow(key = "", value = "") {
        const container = document.getElementById("extra-fields-container");
        const div = document.createElement("div");
        div.className = "extra-field-row";
        const inputKey = createExtraKeyWidget(div, key);
        const inputValue = createExtraValueWidget(key, value);
        inputValue.className = "extra-value";

        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "btn btn-danger";
        btn.style.padding = "6px 10px";
        btn.textContent = "×";
        btn.onclick = function () {
            container.removeChild(div);
            refreshExtraFieldSuggestions();
        };
        div.appendChild(inputKey);
        div.appendChild(inputValue);
        div.appendChild(btn);
        container.appendChild(div);

        if (key === "deepseek_thinking_mode") {
            inputValue.addEventListener(
                "change",
                updateDeepSeekReasoningEffortState,
            );
        }
        refreshExtraFieldSuggestions();
    }

    function findExtraFieldRow(key) {
        const rows = document
            .getElementById("extra-fields-container")
            .getElementsByClassName("extra-field-row");
        return Array.from(rows).find(
            (row) => row.querySelector(".extra-key")?.value === key,
        );
    }

    function removeExtraFieldRow(key) {
        const row = findExtraFieldRow(key);
        if (row) row.remove();
    }

    function ensureDeepSeekThinkingFields() {
        for (const [key, fieldConfig] of Object.entries(
            DEEPSEEK_THINKING_FIELDS,
        )) {
            if (!findExtraFieldRow(key)) {
                addExtraFieldRow(key, fieldConfig.defaultValue);
            }
        }
        updateDeepSeekReasoningEffortState();
    }

    function updateDeepSeekReasoningEffortState() {
        const modeRow = findExtraFieldRow("deepseek_thinking_mode");
        const effortRow = findExtraFieldRow("deepseek_reasoning_effort");
        if (!modeRow || !effortRow) return;
        const mode = modeRow.querySelector(".extra-value")?.value;
        const effortWidget = effortRow.querySelector(".extra-value");
        const enabled = mode === "enabled";
        if (effortWidget) effortWidget.disabled = !enabled;
        effortRow.style.opacity = enabled ? "1" : "0.55";
    }

    function syncDeepSeekThinkingFields(serviceKey) {
        if (serviceKey === "deepseek") ensureDeepSeekThinkingFields();
        onChange();
    }

    window.LlmApiEditorParameters = {
        initialize,
        loadParameters,
        serializeParameters,
        refreshForService,
        findParameterRow,
        focusParameter,
        getParameterValue,
        updateReasoningEffort: updateDeepSeekReasoningEffortState,
    };
})();
