import { config } from "../../package.json";
import { getPref, setPref } from "../utils/prefs";
import axios from "axios";
import {
    emptyLLMApi,
    listApiConfigurations,
    getApiConfiguration,
    getActiveApiConfiguration,
    reloadApiConfigurations,
    saveApiConfiguration,
    removeApiConfigurations,
    moveApiConfigurationToTop,
    type LLMApiData,
    type LLMServiceCatalogEntry,
} from "./apiConfigurations";
import type { PreferenceText } from "./preferences";

function formatExtraDataForDisplay(extraData?: Record<string, any>): string {
    if (
        !extraData ||
        typeof extraData !== "object" ||
        Object.keys(extraData).length === 0
    ) {
        return "";
    }
    const pairs: string[] = [];
    for (const [key, value] of Object.entries(extraData)) {
        if (key && key.trim()) {
            // 截断长值以保持表格整洁
            const displayValue =
                String(value || "").length > 10
                    ? String(value || "").substring(0, 10) + "..."
                    : String(value || "");
            pairs.push(`${key}=${displayValue}`);
        }
    }
    // 限制总长度，避免表格列过宽
    const result = pairs.join(", ");
    return result.length > 50 ? result.substring(0, 47) + "..." : result;
}

export function createApiTableController(
    window: Window,
    prefText: PreferenceText,
) {
    const doc = window.document;
    let cachedKeys: string[] = [];
    function updateCachedLLMApiKeys() {
        cachedKeys = listApiConfigurations().map((api) => api.key);
    }
    function removeSelectedConfigurations() {
        for (const removed of removeApiConfigurations(getLLMApiSelection())) {
            void clearSavedServerCredential(removed.service);
        }
        updateLLMApiTableUI();
    }
    function bindEvents() {
        doc
            .getElementById(
                `zotero-prefpane-${config.addonRef}-next_serviceSelect`,
            )
            ?.addEventListener("change", (event) => {
                const service = (event.target as HTMLSelectElement).value;
                setPref("next_service", service);
                updateConfiguredServiceOptions();
                showLLMApiStatus(
                    prefText(
                        "apiNextServiceSelected",
                        service,
                        prefText(
                            getActiveApiConfiguration(service)
                                ? "apiActive"
                                : "apiNoActiveConfig",
                        ),
                    ),
                );
            });
        doc
            .getElementById(
                `zotero-prefpane-${config.addonRef}-llmapi-table-container`,
            )
            ?.addEventListener("showing", () => updateLLMApiTableUI());
        doc
            .getElementById(`zotero-prefpane-${config.addonRef}-llmapi-add`)
            ?.addEventListener("command", () => {
                void openLLMApiEditDialog();
            });
        doc
            .getElementById(`zotero-prefpane-${config.addonRef}-llmapi-remove`)
            ?.addEventListener("command", removeSelectedConfigurations);
        doc
            .getElementById(`zotero-prefpane-${config.addonRef}-llmapi-edit`)
            ?.addEventListener("command", () => {
                const keys = getLLMApiSelection();
                if (keys.length === 1) void openLLMApiEditDialog(keys[0]);
            });
        doc
            .getElementById(
                `zotero-prefpane-${config.addonRef}-llmapi-activate`,
            )
            ?.addEventListener("command", () => {
                const keys = getLLMApiSelection();
                if (keys.length !== 1) return;
                const api = getApiConfiguration(keys[0]);
                if (!api) return;
                try {
                    saveLLMApiConfiguration(
                        { ...api, activate: !api.activate },
                        api.key,
                    );
                } catch (error) {
                    showLLMApiSaveFailure(error);
                }
            });
        doc
            .getElementById(`zotero-prefpane-${config.addonRef}-llmapi-totop`)
            ?.addEventListener("command", () => {
                const keys = getLLMApiSelection();
                if (keys.length !== 1) return;
                moveApiConfigurationToTop(keys[0]);
                updateLLMApiTableUI(keys[0]);
            });
    }
    async function initialize() {
        if (!addon.data.prefs?.window) return;
        reloadApiConfigurations();
        updateCachedLLMApiKeys();
        const renderLock = Zotero.Promise.defer();
        addon.data.prefs.tableHelper = new ztoolkit.VirtualizedTable(
            addon.data.prefs.window!,
        )
            .setContainerId(
                `zotero-prefpane-${config.addonRef}-llmapi-table-container`,
            )
            .setProp({
                id: `zotero-prefpane-${config.addonRef}-llmapi-table`,
                columns: [
                    {
                        dataKey: "service",
                        label: prefText("colService"),
                        width: 150,
                    },
                    {
                        dataKey: "model",
                        label: prefText("colModel"),
                        width: 200,
                    },
                    {
                        dataKey: "apiUrl",
                        label: prefText("colApiUrl"),
                        width: 140,
                    },
                    {
                        dataKey: "apiKey",
                        label: prefText("colApiKey"),
                        width: 100,
                    },
                    {
                        dataKey: "activate",
                        label: prefText("colActivate"),
                        width: 80,
                    },
                    {
                        dataKey: "extraData",
                        label: prefText("colExtraData"),
                        width: 200,
                    },
                ],
                showHeader: true,
                multiSelect: true,
                staticColumns: false,
                disableFontSizeScaling: true,
            })
            .setProp("getRowCount", () => cachedKeys.length || 0)
            .setProp("getRowData", getRowData)
            .setProp("onSelectionChange", (selection) => {
                const selectedKeys = getLLMApiSelection();
                addon.data.prefs?.window?.document
                    .querySelectorAll(".llmapi-selection")
                    ?.forEach((e) =>
                        setButtonDisabled(
                            e as XULButtonElement,
                            selectedKeys.length === 0,
                        ),
                    );
                addon.data.prefs?.window?.document
                    .querySelectorAll(".llmapi-selection-single")
                    ?.forEach((e) =>
                        setButtonDisabled(
                            e as XULButtonElement,
                            selectedKeys.length !== 1,
                        ),
                    );
            })
            .setProp("onKeyDown", (event: KeyboardEvent) => {
                if (
                    event.key == "Delete" ||
                    (Zotero.isMac && event.key == "Backspace")
                ) {
                    removeSelectedConfigurations();
                    return false;
                }
                return true;
            })
            .render(-1, () => {
                renderLock.resolve();
            });
        await renderLock.promise;
        updateLLMApiTableUI();
        // 强制刷新表格显示所有行;
        setTimeout(() => {
            ztoolkit.log("Forcing table refresh...");
            const tableHelper = (addon.data.prefs as any).tableHelper;
            if (tableHelper && tableHelper.treeInstance) {
                // 强制重新计算行数
                const rowCount = cachedKeys.length || 0;
                // 强制重新渲染
                tableHelper.treeInstance.invalidate();
                tableHelper.render(-1, () => {
                    ztoolkit.log("Forced table refresh completed");
                });
            }
        }, 500);
    }

    async function openLLMApiEditDialog(key?: string) {
        const llmApi = key ? getApiConfiguration(key) : emptyLLMApi;
        if (!llmApi) {
            return false;
        }

        const dialogData = {
            key: llmApi.key,
            service: key
                ? llmApi.service
                : String(getPref("next_service") || ""),
            model: llmApi.model || "",
            apiKey: llmApi.apiKey || "",
            apiUrl: llmApi.apiUrl || "",
            activate: llmApi.activate || false,
            extraData: llmApi.extraData || {},
        };

        // 创建窗口参数
        const windowArgs: {
            _initPromise: any;
            serverUrl: string;
            serviceCatalog: LLMServiceCatalogEntry[];
            llmApiConfigs: LLMApiData[];
            data: {
                key: string;
                service: string;
                model: string;
                apiKey: string;
                apiUrl: string;
                activate: boolean;
                extraData: any;
            };
            isEdit: boolean;
            onSave: (
                data: Omit<LLMApiData, "key">,
                useForTranslation: boolean,
            ) => { success: boolean; message?: string };
            result?: {
                success: boolean;
                data: {
                    service: string;
                    model: string;
                    apiKey: string;
                    apiUrl: string;
                    activate: boolean;
                };
                isEdit: boolean;
                useForTranslation?: boolean;
                persisted?: boolean;
                originalKey?: string;
            };
        } = {
            _initPromise: Zotero.Promise.defer(),
            serverUrl: (getPref("new_serverip")?.toString() || "")
                .trim()
                .replace(/\/+$/, ""),
            serviceCatalog: getLLMServiceCatalog(),
            llmApiConfigs: listApiConfigurations(),
            data: dialogData,
            isEdit: !!key,
            onSave(data, useForTranslation) {
                try {
                    saveLLMApiConfiguration(data, key, useForTranslation);
                    return { success: true };
                } catch (error) {
                    return {
                        success: false,
                        message: showLLMApiSaveFailure(error),
                    };
                }
            },
        };

        // 打开XHTML对话框
        const dialogWindow = Zotero.getMainWindow().openDialog(
            `chrome://${config.addonRef}/content/settings/api-editor/editor.xhtml`,
            `${config.addonRef}-llmApiEditor`,
            `chrome,centerscreen,resizable,status,dialog=no`,
            windowArgs,
        );
        if (!dialogWindow) {
            return false;
        }
        // 等待对话框初始化完成
        await windowArgs._initPromise.promise;
        // 等待对话框关闭
        const result = await new Promise<any>((resolve) => {
            const checkClosed = () => {
                if (dialogWindow.closed) {
                    resolve(windowArgs.result);
                } else {
                    setTimeout(checkClosed, 100);
                }
            };
            checkClosed();
        });

        if (!result || !result.success) {
            return false;
        }
        if (result.persisted) return true;

        const userData = result.data;
        try {
            saveLLMApiConfiguration(
                {
                    ...userData,
                    service: userData.service || userData.serviceselect || "",
                    model: userData.model || userData.modelselect || "",
                },
                key,
                result.useForTranslation === true,
            );
            return true;
        } catch (error) {
            showLLMApiSaveFailure(error);
            return false;
        }
    }

    function saveLLMApiConfiguration(
        data: Omit<LLMApiData, "key">,
        key?: string,
        useForTranslation = false,
    ): LLMApiData {
        const saved = saveApiConfiguration(data, key, useForTranslation);
        updateLLMApiTableUI(saved.key);
        const currentService = String(getPref("next_service") || "");
        showLLMApiStatus(
            prefText(
                "apiSaved",
                saved.service,
                prefText(saved.activate ? "apiActive" : "apiInactive"),
                prefText(
                    saved.activate && currentService === saved.service
                        ? "apiCurrent"
                        : "apiNotCurrent",
                ),
            ),
        );
        return saved;
    }

    function showLLMApiStatus(message: string, failed = false) {
        const status = addon.data.prefs?.window.document.getElementById(
            `zotero-prefpane-${config.addonRef}-llmapi-status`,
        );
        if (!status) return;
        status.textContent = message;
        status.style.color = failed ? "#b42318" : "";
    }

    function showLLMApiSaveFailure(error: unknown): string {
        const message = prefText(
            "apiSaveFailed",
            error instanceof Error
                ? error.message
                : prefText("apiSaveUnknownError"),
        );
        showLLMApiStatus(message, true);
        ztoolkit.log(
            "LLM API configuration save failed:",
            error instanceof Error ? error.name : "UnknownError",
        );
        return message;
    }

    function getLLMServiceCatalog(): LLMServiceCatalogEntry[] {
        const select = addon.data.prefs!.window.document.getElementById(
            `zotero-prefpane-${config.addonRef}-next_serviceSelect`,
        ) as HTMLSelectElement;
        const catalog = new Map(
            (Array.from(select.options) as HTMLOptionElement[])
                .filter(
                    (option) =>
                        option.dataset.pdf2zhConfiguredService !== "true",
                )
                .map(
                    (option) =>
                        [
                            option.value,
                            { value: option.value, label: option.label },
                        ] as const,
                ),
        );
        for (const service of Array.from(
            new Set(listApiConfigurations().map((api) => api.service)),
        )) {
            if (catalog.has(service)) continue;
            catalog.set(service, {
                value: service,
                label: prefText("configuredService", service),
            });
        }
        return Array.from(catalog.values());
    }

    function updateConfiguredServiceOptions() {
        const doc = addon.data.prefs?.window.document;
        const select = doc?.getElementById(
            `zotero-prefpane-${config.addonRef}-next_serviceSelect`,
        ) as HTMLSelectElement | null;
        if (!doc || !select) return;
        const serviceCatalog = getLLMServiceCatalog();
        for (const option of Array.from(
            select.options,
        ) as HTMLOptionElement[]) {
            if (option.dataset.pdf2zhConfiguredService === "true")
                option.remove();
        }
        const values = new Set(
            (Array.from(select.options) as HTMLOptionElement[]).map(
                (option) => option.value,
            ),
        );
        for (const service of serviceCatalog) {
            if (values.has(service.value)) continue;
            const option = doc.createElementNS(
                "http://www.w3.org/1999/xhtml",
                "option",
            ) as HTMLOptionElement;
            option.value = service.value;
            option.textContent = service.label;
            option.dataset.pdf2zhConfiguredService = "true";
            select.appendChild(option);
            values.add(service.value);
        }
        const current = String(getPref("next_service") || "");
        select.value = current;
    }

    function updateLLMApiTableUI(selectedKey?: string) {
        updateCachedLLMApiKeys();
        updateConfiguredServiceOptions();
        setTimeout(() => {
            const tree = addon.data.prefs?.tableHelper?.treeInstance;
            tree?.invalidate();
            if (selectedKey) {
                const index = cachedKeys.indexOf(selectedKey);
                tree?.selection.select(index);
            }
        });
    }

    function setButtonDisabled(button: XUL.Button, disabled: boolean) {
        if (button) {
            button.disabled = disabled;
        }
    }

    function getRowData(index: number) {
        const keys = cachedKeys || [];
        let llmApi = emptyLLMApi;
        if (keys && keys.length > index) {
            const key = keys[index];
            llmApi = getApiConfiguration(key) || emptyLLMApi;
        }
        return {
            key: llmApi.key || "",
            service: llmApi.service || "",
            model: llmApi.model || "",
            apiUrl: llmApi.apiUrl || "",
            apiKey: llmApi.apiKey || "",
            extraData: formatExtraDataForDisplay(llmApi.extraData),
            activate: llmApi.activate ? "✅" : "",
        };
    }

    // 获取 LLM API 选择
    function getLLMApiSelection() {
        const indices =
            addon.data.prefs?.tableHelper?.treeInstance?.selection.selected;
        if (!indices) {
            return [];
        }
        const keys = cachedKeys || [];
        return Array.from(indices).map((i) => keys[i]) || [];
    }

    async function clearSavedServerCredential(service?: string) {
        const normalizedService = (service || "").trim();
        const serverUrl = (getPref("new_serverip")?.toString() || "")
            .trim()
            .replace(/\/+$/, "");
        if (!serverUrl || !normalizedService) return;
        try {
            const response = await axios.post(
                `${serverUrl}/api/llm-api/clear`,
                { service: normalizedService },
                {
                    timeout: 5000,
                    headers: { "Content-Type": "application/json" },
                },
            );
            ztoolkit.log(
                `[llm-api-clear] ${normalizedService} cleared:`,
                response.data?.cleared,
            );
        } catch (error) {
            ztoolkit.log("[llm-api-clear] failed:", normalizedService, error);
        }
    }

    updateCachedLLMApiKeys();
    return {
        initialize,
        bindEvents,
        refresh: updateLLMApiTableUI,
        openEditor: openLLMApiEditDialog,
        getServiceCatalog: getLLMServiceCatalog,
        save: saveLLMApiConfiguration,
    };
}
