export type TableMode = "preserve" | "fixed" | "adaptive";

/** Apply prettier table processing only when both table options are enabled. */
export function tableModeFromPref(
    value: unknown,
    translateTableText: unknown,
): TableMode | "" {
    return translateTableText === true && value === true ? "fixed" : "";
}

/** Missing capabilities mean an old Server; malformed responses remain errors. */
export function supportsTableMode(mode: TableMode, payload: unknown): boolean {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        throw new Error("Invalid Server capability response.");
    }
    if (!("tableModes" in payload)) return false;
    const modes = payload.tableModes;
    if (
        !Array.isArray(modes) ||
        modes.some((value) => typeof value !== "string")
    ) {
        throw new Error("Invalid Server tableModes capability.");
    }
    return modes.includes(mode);
}

/** Capability negotiation for opt-in Reference Skip and older Servers. */
export function supportsReferenceSkip(payload: unknown): boolean {
    return (
        payload !== null &&
        typeof payload === "object" &&
        !Array.isArray(payload) &&
        "referenceSkip" in payload &&
        payload.referenceSkip === true
    );
}

/** Prevent DeepSeek Flash jobs from reaching an outdated Server. */
export function needsDeepSeekFlashPatch(settings: unknown): boolean {
    if (!settings || typeof settings !== "object") return false;
    const data = settings as { service?: unknown; model?: unknown };
    return (
        data.service === "deepseek" &&
        typeof data.model === "string" &&
        data.model.trim() === "deepseek-flash"
    );
}

export function supportsDeepSeekFlashPatch(payload: unknown): boolean {
    return (
        payload !== null &&
        typeof payload === "object" &&
        !Array.isArray(payload) &&
        "deepseekFlashThinkingPatch" in payload &&
        payload.deepseekFlashThinkingPatch === true
    );
}

const SERVICE_ALIASES: Record<string, string> = {
    ModelScope: "modelscope",
    openailiked: "openaicompatible",
    tencent: "tencentmechinetranslation",
    silicon: "siliconflow",
    "qwen-mt": "qwenmt",
    AliyunDashScope: "aliyundashscope",
    "azure-openai": "azureopenai",
};

const BUILTIN_SERVICES = new Set([
    "bing",
    "google",
    "argos",
    "clitranslator",
    "deepl",
    "openai",
    "aliyundashscope",
    "xinference",
    "ollama",
    "azureopenai",
    "modelscope",
    "zhipu",
    "siliconflow",
    "siliconflowfree",
    "tencentmechinetranslation",
    "gemini",
    "azure",
    "anythingllm",
    "dify",
    "grok",
    "groq",
    "deepseek",
    "qwenmt",
    "openaicompatible",
    "claudecode",
]);

/** Custom service names and relay fields need the matching Server protocol. */
export function needsRelayPatch(settings: unknown): boolean {
    if (!settings || typeof settings !== "object" || Array.isArray(settings)) {
        return false;
    }
    const data = settings as {
        service?: unknown;
        extraData?: Record<string, unknown>;
    };
    const service = typeof data.service === "string" ? data.service.trim() : "";
    if (!service) return false;
    const canonical = SERVICE_ALIASES[service] || service;
    if (!BUILTIN_SERVICES.has(canonical)) return true;
    if (canonical !== "openai" && canonical !== "openaicompatible")
        return false;
    const extra = data.extraData;
    return (
        extra !== null &&
        typeof extra === "object" &&
        !Array.isArray(extra) &&
        ["zotero_api_format", "zotero_extra_headers", "zotero_extra_body"].some(
            (key) => extra[key] !== undefined && extra[key] !== "",
        )
    );
}

/** Protocol 2 adds isolated task configuration and complete-response checks. */
export function supportsRelayPatch(payload: unknown): boolean {
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        return false;
    }
    const capabilities = payload as {
        relayPatch?: unknown;
        relayPatchVersion?: unknown;
    };
    return (
        capabilities.relayPatch === true &&
        typeof capabilities.relayPatchVersion === "number" &&
        Number.isInteger(capabilities.relayPatchVersion) &&
        capabilities.relayPatchVersion >= 2
    );
}
