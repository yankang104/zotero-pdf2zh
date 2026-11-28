import { getPref, setPref, clearPref } from "../utils/prefs";

export interface LLMServiceConfig {
    name: string;
    models?: string[];
    urls?: string[];
    extraData?: any[];
}

export interface LLMServiceCatalogEntry {
    value: string;
    label: string;
}

export interface LLMApiData {
    key: string;
    // 服务商名称用于配置选择，API 协议保存在 extraData 中。
    service: string;
    apiKey: string;
    apiUrl: string;
    model: string;
    activate: boolean;
    extraData?: Record<string, any>;
}

export const emptyLLMApi: LLMApiData = {
    key: "",
    service: "",
    apiKey: "",
    apiUrl: "",
    model: "",
    activate: false,
    extraData: {},
};

// Zotero preferences are persistent storage; this is the only loaded API map.
const configurations = new Map<string, LLMApiData>();

export function listApiConfigurations(): LLMApiData[] {
    return Array.from(configurations.values());
}

export function getApiConfiguration(key: string): LLMApiData | undefined {
    return configurations.get(key);
}

export function getActiveApiConfiguration(
    service: string,
): LLMApiData | undefined {
    return listApiConfigurations().find(
        (api) => api.service === service && api.activate,
    );
}

function replaceConfigurations(entries: LLMApiData[]) {
    configurations.clear();
    for (const api of entries) {
        if (api.activate) {
            for (const previous of configurations.values()) {
                if (previous.service === api.service) previous.activate = false;
            }
        }
        configurations.set(api.key, api);
    }
}

function migrateLegacyDeepSeekConfig(llmApi: LLMApiData): boolean {
    if (llmApi.service !== "deepseek") return false;
    if (
        llmApi.model !== "deepseek-chat" &&
        llmApi.model !== "deepseek-reasoner"
    ) {
        return false;
    }

    const legacyModel = llmApi.model;
    llmApi.model = "deepseek-v4-flash";
    llmApi.extraData = llmApi.extraData || {};

    // Preserve an explicitly saved thinking choice. Otherwise map the retired
    // aliases to their V4 Flash semantics.
    if (!("deepseek_thinking_mode" in llmApi.extraData)) {
        if (legacyModel === "deepseek-reasoner") {
            llmApi.extraData.deepseek_thinking_mode = "enabled";
            llmApi.extraData.deepseek_reasoning_effort = "high";
        } else {
            llmApi.extraData.deepseek_thinking_mode = "disabled";
            delete llmApi.extraData.deepseek_reasoning_effort;
        }
    }
    return true;
}

export function reloadApiConfigurations(): void {
    configurations.clear();
    const stored = getPref("llmApis");
    if (!stored || typeof stored !== "string") return;
    try {
        const entries = JSON.parse(stored);
        if (!Array.isArray(entries)) return;
        let changed = false;
        const activeServices = new Set<string>();
        const loaded: LLMApiData[] = [];
        for (const api of entries as LLMApiData[]) {
            if (!api.key || !api.service) continue;
            changed = migrateLegacyDeepSeekConfig(api) || changed;
            if (api.activate === undefined) api.activate = false;
            if (!api.extraData) api.extraData = {};
            if (api.activate) {
                changed = activeServices.has(api.service) || changed;
                activeServices.add(api.service);
            }
            loaded.push(api);
        }
        replaceConfigurations(loaded);
        if (changed)
            setPref("llmApis", JSON.stringify(listApiConfigurations()));
    } catch (error) {
        configurations.clear();
        ztoolkit.log(
            "Error loading LLM APIs from prefs:",
            error instanceof Error ? error.name : "Unknown error",
        );
    }
}

export function saveApiConfiguration(
    data: Omit<LLMApiData, "key">,
    key?: string,
    useForTranslation = false,
): LLMApiData {
    const service = String(data.service || "").trim();
    if (!service)
        throw new Error(
            String(Zotero.locale || "en").startsWith("zh")
                ? "请填写 LLM 服务名称。"
                : "Enter an LLM service name.",
        );
    const saved: LLMApiData = {
        key: key || Zotero.Utilities.generateObjectKey(),
        service,
        model: String(data.model || "").trim(),
        apiKey: String(data.apiKey || "").trim(),
        apiUrl: String(data.apiUrl || "").trim(),
        activate: useForTranslation || data.activate === true,
        extraData: data.extraData || {},
    };
    const originalConfiguration = getApiConfiguration(saved.key);
    const renamedSelectedService =
        originalConfiguration?.activate &&
        originalConfiguration.service !== service &&
        getPref("next_service") === originalConfiguration.service;
    const entries = JSON.parse(
        JSON.stringify(listApiConfigurations()),
    ) as LLMApiData[];
    const index = entries.findIndex((api) => api.key === saved.key);
    if (index < 0) entries.push(saved);
    else entries[index] = saved;
    if (saved.activate) {
        for (const api of entries) {
            if (api.key !== saved.key && api.service === service) {
                api.activate = false;
            }
        }
    }
    const changes: Array<[string, string]> = [
        ["llmApis", JSON.stringify(entries)],
    ];
    if (useForTranslation) {
        changes.push(["next_service", service], ["engine", "pdf2zh_next"]);
    } else if (renamedSelectedService) {
        changes.push(["next_service", service]);
    }
    const previous = changes.map(([name]) => [name, getPref(name)] as const);
    try {
        for (const [name, value] of changes) setPref(name, value);
    } catch (error) {
        for (const [name, value] of previous.reverse()) {
            try {
                if (
                    typeof value === "string" ||
                    typeof value === "number" ||
                    typeof value === "boolean"
                ) {
                    setPref(name, value);
                } else {
                    clearPref(name);
                }
            } catch {
                // The original write failure is shown; reopening preferences
                // reloads whichever settings Zotero was able to persist.
            }
        }
        throw error;
    }
    replaceConfigurations(entries);
    return saved;
}

export function removeApiConfigurations(keys: string[]): LLMApiData[] {
    const removed = listApiConfigurations().filter((api) =>
        keys.includes(api.key),
    );
    const remaining = listApiConfigurations().filter(
        (api) => !keys.includes(api.key),
    );
    setPref("llmApis", JSON.stringify(remaining));
    replaceConfigurations(remaining);
    return removed;
}

export function moveApiConfigurationToTop(key: string): void {
    const api = configurations.get(key);
    if (!api) return;
    const entries = [
        api,
        ...listApiConfigurations().filter((item) => item.key !== key),
    ];
    setPref("llmApis", JSON.stringify(entries));
    replaceConfigurations(entries);
}
