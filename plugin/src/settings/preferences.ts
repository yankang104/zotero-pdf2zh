import { config } from "../../package.json";
import { getPref, setPref } from "../utils/prefs";
import { getString } from "../utils/locale";
import axios from "axios";
import { createApiTableController } from "./apiTable";

const PREF_UI_TEXT = {
    zh: {
        invalidFont: "文件类型无效，请选择 .ttf、.otf、.woff 或 .woff2 文件。",
        colService: "服务",
        colModel: "模型",
        colApiUrl: "API URL",
        colApiKey: "API Key",
        colActivate: "激活",
        colExtraData: "额外参数",
        configuredService: (service: string) => `${service}（已配置）`,
        apiSaved: (service: string, active: string, current: string) =>
            `已保存「${service}」。${active}；${current}。`,
        apiActive: "此配置已激活",
        apiInactive: "此配置未激活",
        apiCurrent: "当前翻译正在使用此配置",
        apiNotCurrent: "尚未选为当前翻译服务",
        apiSaveFailed: (message: string) => `配置保存失败：${message}`,
        apiServiceRequired: "请填写 LLM 服务名称。",
        apiSaveUnknownError: "无法写入 Zotero 设置，请重试。",
        apiNextServiceSelected: (service: string, active: string) =>
            `PDF2zh Next 翻译服务已设为「${service}」。${active}。`,
        apiNoActiveConfig: "尚无已激活的 API 配置；免配置服务无需 API 配置",
        serverAddressRequired: "请先设置 Server IP 地址",
        connectionTitle: "Server 连接检查",
        checking: "正在检查 Server 连接...",
        unknown: "未知",
        successLine: (version: string) => `✓ 连接成功！Server 版本: ${version}`,
        successAlert: (url: string, version: string) =>
            `✓ 连接成功！\n\nServer 地址: ${url}\nServer 版本: ${version}\n状态: 正常运行`,
        badStatus: (status: number) => `Server 返回错误状态: ${status}`,
        unknownError: "未知错误",
        timeout: "连接超时（10秒）",
        timeoutHelp:
            "可能原因:\n1. 网络连接不稳定\n2. 防火墙阻止了连接\n3. Server 响应时间过长\n\n建议:\n- 检查网络连接\n- 临时关闭防火墙测试\n- 确认 Server 已正常启动",
        responseError: (status: number) => `Server 返回错误: ${status}`,
        responseHelp:
            "可能原因:\n1. Server 版本过旧，不支持 /health 端点\n2. Server 配置错误\n\n建议:\n- 更新 Server 到最新版本\n- 检查 Server 日志查看错误详情",
        cannotConnect: "无法连接到 Server",
        cannotConnectHelp: (url: string) =>
            "可能原因:\n1. Server 未启动\n2. 插件里的地址/端口和终端不一致\n3. 该端口被其他程序占用\n\n建议:\n- 打开 Server 终端，看它打印的 http://127.0.0.1:端口\n- 把插件里的 Python Server IP 改成和终端完全一样\n- 当前检查的是: " +
            url,
        wrongService: "这个地址上不是 PDF2zh Server",
        wrongServiceHelp: (url: string) =>
            "当前检查的是 " +
            url +
            "\n这个端口有响应，但不是 PDF2zh（常见是被其他程序占用）。\n请看 Server 终端里实际打印的地址，把插件里的 Python Server IP 改成那个地址。",
        genericHelp: "请检查网络连接和 Server 状态",
        failureLine: (message: string) => `✗ 连接失败: ${message}`,
        failureAlert: (message: string, help: string) =>
            `✗ 连接失败\n\n错误信息: ${message}\n\n${help}`,
    },
    en: {
        invalidFont:
            "Invalid file type. Select a .ttf, .otf, .woff, or .woff2 file.",
        colService: "Service",
        colModel: "Model",
        colApiUrl: "API URL",
        colApiKey: "API Key",
        colActivate: "Active",
        colExtraData: "Extra Parameters",
        configuredService: (service: string) => `${service} (configured)`,
        apiSaved: (service: string, active: string, current: string) =>
            `Saved "${service}". ${active}; ${current}.`,
        apiActive: "This configuration is active",
        apiInactive: "This configuration is inactive",
        apiCurrent: "This configuration is selected for translation",
        apiNotCurrent: "Not selected as the current translation service",
        apiSaveFailed: (message: string) =>
            `Could not save configuration: ${message}`,
        apiServiceRequired: "Enter an LLM service name.",
        apiSaveUnknownError: "Could not write Zotero settings. Try again.",
        apiNextServiceSelected: (service: string, active: string) =>
            `PDF2zh Next translation service is "${service}". ${active}.`,
        apiNoActiveConfig:
            "No active API configuration; keyless services do not need one",
        serverAddressRequired: "Set the Server IP address first.",
        connectionTitle: "Server Connection Check",
        checking: "Checking Server connection...",
        unknown: "Unknown",
        successLine: (version: string) =>
            `✓ Connected. Server version: ${version}`,
        successAlert: (url: string, version: string) =>
            `✓ Connected successfully.\n\nServer: ${url}\nVersion: ${version}\nStatus: Running`,
        badStatus: (status: number) => `Server returned status ${status}`,
        unknownError: "Unknown error",
        timeout: "Connection timed out (10 seconds)",
        timeoutHelp:
            "Possible causes:\n1. Unstable network\n2. A firewall is blocking the connection\n3. The Server is responding slowly\n\nTry:\n- Check your network\n- Temporarily test without the firewall\n- Confirm the Server is running",
        responseError: (status: number) => `Server returned error ${status}`,
        responseHelp:
            "Possible causes:\n1. The Server is too old to provide /health\n2. Server configuration error\n\nTry:\n- Update the Server\n- Check the Server terminal logs",
        cannotConnect: "Cannot connect to the Server",
        cannotConnectHelp: (url: string) =>
            "Possible causes:\n1. The Server is not running\n2. The plugin URL/port does not match the terminal\n3. Another program is using that port\n\nTry:\n- Check the http://127.0.0.1:PORT printed in the Server terminal\n- Set Python Server IP in the plugin to that exact address\n- Currently checking: " +
            url,
        wrongService: "This address is not a PDF2zh Server",
        wrongServiceHelp: (url: string) =>
            "Checked " +
            url +
            "\nSomething responded, but it is not PDF2zh (another program may be using this port).\nCopy the address printed in the Server terminal into Python Server IP.",
        genericHelp: "Check the network connection and Server status.",
        failureLine: (message: string) => `✗ Connection failed: ${message}`,
        failureAlert: (message: string, help: string) =>
            `✗ Connection failed\n\nError: ${message}\n\n${help}`,
    },
} as const;

function preferenceUiLanguage(): "zh" | "en" {
    const locale = String(Zotero.locale || "en-US").toLowerCase();
    return locale.startsWith("zh") ? "zh" : "en";
}

export function prefText(
    key: keyof (typeof PREF_UI_TEXT)["en"],
    ...args: any[]
) {
    const value: any = (PREF_UI_TEXT as any)[preferenceUiLanguage()][key];
    return typeof value === "function" ? value(...args) : value;
}

export type PreferenceText = typeof prefText;

export function registerPreferences() {
    setPref("engine", "pdf2zh_next");
    Zotero.PreferencePanes.register({
        pluginID: addon.data.config.addonID,
        src: rootURI + "content/settings/preferences.xhtml",
        label: getString("prefs-title"),
        image: `chrome://${addon.data.config.addonRef}/content/icons/favicon.svg`,
    });
}

export async function registerPrefsScripts(window: Window) {
    addon.data.prefs = { window, columns: [], rows: [] };
    const apiTable = createApiTableController(window, prefText);
    bindPrefEvents();
    apiTable.bindEvents();
    await apiTable.initialize();
    initializeRenameStyle();
}

function bindPrefEvents() {
    const { window } = addon.data.prefs ?? {};
    if (!window) return;
    const doc = window.document;
    if (!doc) return;
    const translateTableCheckbox = doc.getElementById(
        `zotero-prefpane-${config.addonRef}-translateTableText`,
    ) as XUL.Checkbox | null;
    const prettierTableCheckbox = doc.getElementById(
        `zotero-prefpane-${config.addonRef}-prettierTables`,
    ) as XUL.Checkbox | null;
    if (translateTableCheckbox && prettierTableCheckbox) {
        prettierTableCheckbox.disabled = getPref("translateTableText") !== true;
        const syncTableOptions = () => {
            prettierTableCheckbox.disabled = !translateTableCheckbox.checked;
        };
        translateTableCheckbox.addEventListener("command", syncTableOptions);
        translateTableCheckbox.addEventListener("change", syncTableOptions);
    }
    // 为SourceLangSelect和TargetLangSelect添加html:option
    const sourceLangSelect = doc.getElementById(
        `zotero-prefpane-${config.addonRef}-sourceLangSelect`,
    );
    const targetLangSelect = doc.getElementById(
        `zotero-prefpane-${config.addonRef}-targetLangSelect`,
    );
    for (const [langName, langCode] of Object.entries(lang_map)) {
        const option = doc.createElement("option");
        option.value = langCode;
        option.textContent = langName;
        sourceLangSelect?.appendChild(option.cloneNode(true));
        targetLangSelect?.appendChild(option.cloneNode(true));
    }
    const renameStyleSelect = doc.querySelector(
        `#zotero-prefpane-${config.addonRef}-renameStyle`,
    );
    renameStyleSelect?.addEventListener("change", (e) => {
        const value = (e.target as HTMLSelectElement).value;
        if (value) {
            setPref("renameStyle", value);
            handleRenameStyleChange(value);
        }
    });

    // ********************* Server连接检查 *********************
    // 新增：测试Server连接按钮事件
    doc
        .querySelector(`#zotero-prefpane-${config.addonRef}-checkConnection`)
        ?.addEventListener("click", async () => {
            await checkServerConnection();
        });
}

function initializeRenameStyle() {
    const { window } = addon.data.prefs ?? {};
    if (!window) {
        ztoolkit.log("Window object not found");
        return;
    }
    // 延迟执行，确保DOM完全加载
    setTimeout(() => {
        const renameStyleSelect = window.document.querySelector(
            `#zotero-prefpane-${config.addonRef}-renameStyle`,
        ) as HTMLSelectElement | null;
        if (renameStyleSelect) {
            handleRenameStyleChange(renameStyleSelect.value);
        }
    }, 100);
}

// 附件标题格式切换处理函数 (#310)
function handleRenameStyleChange(style: string) {
    const { window } = addon.data.prefs ?? {};
    if (!window) return;
    const showPrefixLength = style === "titlePrefix";
    const showTemplate = style === "custom";
    const prefixInputs = window.document.getElementsByClassName(
        "rename-prefix-length",
    );
    for (const el of prefixInputs as any as HTMLElement[]) {
        el.style.display = showPrefixLength ? "" : "none";
    }
    const templateInputs =
        window.document.getElementsByClassName("rename-template");
    for (const el of templateInputs as any as HTMLElement[]) {
        el.style.display = showTemplate ? "" : "none";
    }
}

const lang_map = {
    English: "en",
    "Simplified Chinese": "zh-CN",
    "Traditional Chinese - Hong Kong": "zh-HK",
    "Traditional Chinese - Taiwan": "zh-TW",
    Japanese: "ja",
    Korean: "ko",
    Polish: "pl",
    Russian: "ru",
    Spanish: "es",
    Portuguese: "pt",
    "Brazilian Portuguese": "pt-BR",
    French: "fr",
    Malay: "ms",
    Indonesian: "id",
    Turkmen: "tk",
    "Filipino (Tagalog)": "tl",
    Vietnamese: "vi",
    "Kazakh (Latin)": "kk",
    German: "de",
    Dutch: "nl",
    Irish: "ga",
    Italian: "it",
    Greek: "el",
    Swedish: "sv",
    Danish: "da",
    Norwegian: "no",
    Icelandic: "is",
    Finnish: "fi",
    Ukrainian: "uk",
    Czech: "cs",
    Romanian: "ro",
    Hungarian: "hu",
    Slovak: "sk",
    Croatian: "hr",
    Estonian: "et",
    Latvian: "lv",
    Lithuanian: "lt",
    Belarusian: "be",
    Macedonian: "mk",
    Albanian: "sq",
    "Serbian (Cyrillic)": "sr",
    Slovenian: "sl",
    Catalan: "ca",
    Bulgarian: "bg",
    Maltese: "mt",
    Swahili: "sw",
    Amharic: "am",
    Oromo: "om",
    Tigrinya: "ti",
    "Haitian Creole": "ht",
    Latin: "la",
    Lao: "lo",
    Malayalam: "ml",
    Gujarati: "gu",
    Thai: "th",
    Burmese: "my",
    Tamil: "ta",
    Telugu: "te",
    Oriya: "or",
    Armenian: "hy",
    "Mongolian (Cyrillic)": "mn",
    Georgian: "ka",
    Khmer: "km",
    Bosnian: "bs",
    Luxembourgish: "lb",
    Romansh: "rm",
    Turkish: "tr",
    Sinhala: "si",
    Uzbek: "uz",
    Kyrgyz: "ky",
    Tajik: "tg",
    Abkhazian: "ab",
    Afar: "aa",
    Afrikaans: "af",
    Akan: "ak",
    Aragonese: "an",
    Avaric: "av",
    Ewe: "ee",
    Aymara: "ay",
    Ojibwa: "oj",
    Occitan: "oc",
    Ossetian: "os",
    Pali: "pi",
    Bashkir: "ba",
    Basque: "eu",
    Breton: "br",
    Chamorro: "ch",
    Chechen: "ce",
    Chuvash: "cv",
    Tswana: "tn",
    "Ndebele, South": "nr",
    Ndonga: "ng",
    Faroese: "fo",
    Fijian: "fj",
    "Frisian, Western": "fy",
    Ganda: "lg",
    Kongo: "kg",
    Kalaallisut: "kl",
    "Church Slavic": "cu",
    Guarani: "gn",
    Interlingua: "ia",
    Herero: "hz",
    Kikuyu: "ki",
    Rundi: "rn",
    Kinyarwanda: "rw",
    Galician: "gl",
    Kanuri: "kr",
    Cornish: "kw",
    Komi: "kv",
    Xhosa: "xh",
    Corsican: "co",
    Cree: "cr",
    Quechua: "qu",
    "Kurdish (Latin)": "ku",
    Kuanyama: "kj",
    Limburgan: "li",
    Lingala: "ln",
    Manx: "gv",
    Malagasy: "mg",
    Marshallese: "mh",
    Maori: "mi",
    Navajo: "nv",
    Nauru: "na",
    Nyanja: "ny",
    "Norwegian Nynorsk": "nn",
    Sardinian: "sc",
    "Northern Sami": "se",
    Samoan: "sm",
    Sango: "sg",
    Shona: "sn",
    Esperanto: "eo",
    "Scottish Gaelic": "gd",
    Somali: "so",
    "Southern Sotho": "st",
    Tatar: "tt",
    Tahitian: "ty",
    Tongan: "to",
    Twi: "tw",
    Walloon: "wa",
    Welsh: "cy",
    Venda: "ve",
    Volapük: "vo",
    Interlingue: "ie",
    "Hiri Motu": "ho",
    Igbo: "ig",
    Ido: "io",
    Inuktitut: "iu",
    Inupiaq: "ik",
    "Sichuan Yi": "ii",
    Yoruba: "yo",
    Zhuang: "za",
    Tsonga: "ts",
    Zulu: "zu",
};

async function checkServerConnection() {
    const serverUrl = getPref("new_serverip")?.toString() || "";
    if (!serverUrl) {
        ztoolkit.getGlobal("alert")(prefText("serverAddressRequired"));
        return;
    }

    const progressWindow = new ztoolkit.ProgressWindow(
        prefText("connectionTitle"),
        { closeOnClick: false, closeTime: -1 },
    ).createLine({
        text: prefText("checking"),
        type: "default",
        progress: 50,
    });
    progressWindow.show();

    try {
        const response = await axios.get(`${serverUrl}/health`, {
            timeout: 10000,
            headers: { "Content-Type": "application/json" },
        });
        if (response.status !== 200 || !response.data) {
            throw new Error(prefText("badStatus", response.status));
        }

        const data = response.data;
        if (
            !data ||
            typeof data !== "object" ||
            (data.status !== "ok" && !data.version)
        ) {
            throw new Error(prefText("wrongService"));
        }
        const version = data.version || prefText("unknown");
        ztoolkit.log("Server connection succeeded:", data);
        progressWindow.changeLine({
            text: prefText("successLine", version),
            type: "success",
            progress: 100,
        });
        setTimeout(() => {
            progressWindow.close();
            ztoolkit.getGlobal("alert")(
                prefText("successAlert", serverUrl, version),
            );
        }, 1000);
    } catch (error) {
        ztoolkit.log("Server connection failed:", error);
        let errorMsg = prefText("unknownError");
        let troubleshooting = prefText("genericHelp");

        if (axios.isAxiosError(error)) {
            if (
                error.code === "ECONNABORTED" ||
                error.message.includes("timeout")
            ) {
                errorMsg = prefText("timeout");
                troubleshooting = prefText("timeoutHelp");
            } else if (error.response) {
                if (
                    error.response.status === 401 ||
                    error.response.status === 403 ||
                    error.response.status === 404
                ) {
                    errorMsg = prefText("wrongService");
                    troubleshooting = prefText("wrongServiceHelp", serverUrl);
                } else {
                    errorMsg = prefText("responseError", error.response.status);
                    troubleshooting = prefText("responseHelp");
                }
            } else if (error.request) {
                errorMsg = prefText("cannotConnect");
                troubleshooting = prefText("cannotConnectHelp", serverUrl);
            } else {
                errorMsg = error.message;
            }
        } else if (error instanceof Error) {
            errorMsg = error.message;
            if (errorMsg === prefText("wrongService")) {
                troubleshooting = prefText("wrongServiceHelp", serverUrl);
            }
        }

        progressWindow.changeLine({
            text: prefText("failureLine", errorMsg),
            type: "error",
            progress: 100,
        });
        setTimeout(() => {
            progressWindow.close();
            ztoolkit.getGlobal("alert")(
                prefText("failureAlert", errorMsg, troubleshooting),
            );
        }, 1500);
    }
}
