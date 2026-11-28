/* eslint-disable no-restricted-globals */
/* global AbortController, clearTimeout, document, fetch, setTimeout, URL, window */

(() => {
    "use strict";

    const SERVICES_WITHOUT_MODEL_LIST = new Set([
        "bing",
        "google",
        "argos",
        "claudecode",
        "deepl",
        "tencent",
        "tencentmechinetranslation",
        "azure",
        "dify",
        "anythingllm",
    ]);

    function modelListUrl(baseUrl, service, apiFormat = "chat") {
        const url = new URL(baseUrl);
        let path = url.pathname.replace(/\/+$/, "");
        if (service === "ollama") {
            path = path.replace(
                /\/(?:api\/tags|api\/generate|api\/chat|v1(?:\/models|\/chat\/completions)?)$/,
                "",
            );
            path += path.endsWith("/api") ? "/tags" : "/api/tags";
        } else {
            path = path.replace(
                /\/(?:chat\/completions|responses|messages)$/,
                "",
            );
            if (!path.endsWith("/models")) {
                if (
                    (service === "xinference" ||
                        (apiFormat === "messages" && service !== "gemini")) &&
                    !/\/v\d+[a-z0-9]*$/i.test(path)
                ) {
                    path += "/v1";
                }
                path += "/models";
            }
        }
        url.pathname = path;
        url.hash = "";
        return url.href;
    }

    function modelRequestSpec(config) {
        const extraData = config.extraData || {};
        const apiFormat = extraData.zotero_api_format || "chat";
        const authMode = extraData.zotero_auth_mode || "auto";
        const rawHeaders = extraData.zotero_extra_headers || {};
        const customHeaders =
            typeof rawHeaders === "string"
                ? JSON.parse(rawHeaders)
                : rawHeaders;
        const headers = window.LlmApiEditorRequestHeaders.buildRequestHeaders(
            apiFormat,
            config.apiKey,
            customHeaders,
            false,
            authMode,
        );
        const url = modelListUrl(config.apiUrl, config.service, apiFormat);
        if (config.service === "gemini" && authMode === "auto") {
            const compatible = /\/openai(?:\/|$)/.test(new URL(url).pathname);
            const automaticName =
                apiFormat === "messages" ? "x-api-key" : "authorization";
            const customNames = new Set(
                Object.keys(customHeaders).map((name) => name.toLowerCase()),
            );
            for (const name of Object.keys(headers)) {
                if (
                    name.toLowerCase() === automaticName &&
                    !customNames.has(automaticName)
                ) {
                    delete headers[name];
                }
            }
            const credentialName = compatible
                ? "Authorization"
                : "x-goog-api-key";
            if (!customNames.has(credentialName.toLowerCase())) {
                headers[credentialName] = compatible
                    ? `Bearer ${config.apiKey || ""}`
                    : String(config.apiKey || "");
            }
        }
        return { url, headers };
    }

    function extractModelIds(payload) {
        const result = payload?.result;
        const candidates = Array.isArray(payload)
            ? [payload]
            : [payload?.data, payload?.models, result?.data, result];
        const entries = candidates.find(Array.isArray) || [];
        return [
            ...new Set(
                entries
                    .map((entry) =>
                        typeof entry === "string"
                            ? entry
                            : entry?.id ||
                              entry?.name ||
                              entry?.model ||
                              entry?.model_name ||
                              "",
                    )
                    .filter(Boolean)
                    .map((value) => String(value).replace(/^models\//, "")),
            ),
        ];
    }

    function requestError(kind, status) {
        const error = new Error(kind);
        error.kind = kind;
        error.status = status;
        return error;
    }

    function transportError(error) {
        const status = error.status || error.xmlhttp?.status;
        if (status) return requestError("http", status);
        const timeout =
            error.name === "AbortError" ||
            /timeout|timed\s*out/i.test(`${error.name} ${error.message}`);
        return requestError(timeout ? "timeout" : "network");
    }

    async function requestJson(url, headers, http) {
        if (http?.request) {
            let response;
            try {
                response = await http.request("GET", url, {
                    headers,
                    responseType: "text",
                    timeout: 20000,
                    errorDelayMax: 0,
                });
            } catch (error) {
                throw transportError(error);
            }
            if (response.status < 200 || response.status >= 300) {
                throw requestError("http", response.status);
            }
            try {
                return JSON.parse(response.responseText || response.response);
            } catch {
                throw requestError("nonJson");
            }
        }

        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), 20000);
        try {
            let response;
            try {
                response = await fetch(url, {
                    method: "GET",
                    headers,
                    signal: controller.signal,
                });
            } catch (error) {
                throw transportError(error);
            }
            if (!response.ok) throw requestError("http", response.status);
            try {
                return await response.json();
            } catch (error) {
                if (controller.signal.aborted) throw requestError("timeout");
                throw requestError("nonJson");
            }
        } finally {
            clearTimeout(timeout);
        }
    }

    function failureMessage(error, t) {
        if (error.kind === "http") {
            const statusMessages = {
                401: "modelUnauthorized",
                403: "modelForbidden",
                404: "modelNotFound",
            };
            return t(
                statusMessages[error.status] || "modelHttpError",
                error.status,
            );
        }
        return t(
            {
                timeout: "modelTimeout",
                network: "modelNetworkError",
                nonJson: "modelNonJson",
            }[error.kind] || "modelSettingsError",
        );
    }

    function initialize(options) {
        const {
            getCurrentConfig,
            getModel,
            updateModels,
            t,
            actionsContainer,
            statusElement,
            http,
        } = options;
        const actions =
            actionsContainer ||
            document.getElementById("model").closest(".form-group");

        const button = document.createElement("button");
        button.type = "button";
        button.id = "fetch-models-btn";
        button.className = "btn btn-secondary btn-compact";
        button.textContent = t("fetchModels");
        actions.appendChild(button);

        const status =
            statusElement ||
            actions.appendChild(document.createElement("span"));
        status.id = "fetch-models-status";
        status.classList.add("model-fetch-status");
        status.setAttribute("aria-live", "polite");

        function showResult(message, isError = false) {
            status.textContent = message;
            status.title = message;
            status.classList.toggle("error", isError);
        }

        async function fetchModels() {
            const config = getCurrentConfig();
            if (SERVICES_WITHOUT_MODEL_LIST.has(config.service)) {
                showResult(t("modelListUnavailable"));
                return;
            }
            if (!config.apiUrl) {
                showResult(t("baseUrlRequired"), true);
                return;
            }
            const model = getModel();
            button.disabled = true;
            button.textContent = t("fetching");
            showResult(t("fetching"));

            try {
                const spec = modelRequestSpec(config);
                const payload = await requestJson(spec.url, spec.headers, http);
                const models = extractModelIds(payload);
                const sameService =
                    getCurrentConfig().service === config.service;
                updateModels(
                    config.service,
                    models,
                    sameService ? getModel() : model,
                );
                if (sameService) {
                    showResult(
                        models.length
                            ? t("fetched", models.length)
                            : t("noModels"),
                    );
                }
            } catch (error) {
                if (getCurrentConfig().service === config.service) {
                    showResult(t("failed", failureMessage(error, t)), true);
                }
            } finally {
                button.disabled = false;
                button.textContent = t("fetchModels");
            }
        }

        button.addEventListener("click", fetchModels);
        for (const fieldId of ["service", "apiUrl"]) {
            const field = document.getElementById(fieldId);
            field.addEventListener("input", () => showResult(""));
            field.addEventListener("change", () => showResult(""));
        }
    }

    window.LlmApiEditorModels = {
        initialize,
        modelListUrl,
        modelRequestSpec,
        extractModelIds,
    };
})();
