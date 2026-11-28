// lifecycle hooks
import { registerContextMenu } from "./menus/contextMenu";
import { processSelectedDocuments } from "./translation/workflow";
import { initLocale } from "./utils/locale";
import {
    registerPreferences,
    registerPrefsScripts,
} from "./settings/preferences";

async function onStartup() {
    await Promise.all([
        Zotero.initializationPromise,
        Zotero.unlockPromise,
        Zotero.uiReadyPromise,
    ]);
    initLocale(); // 初始化多语言
    registerPreferences();
    await Promise.all(
        Zotero.getMainWindows().map((win) => onMainWindowLoad(win)),
    );
}

async function onMainWindowLoad(win: Window): Promise<void> {
    registerContextMenu(win);
}

async function onPrefsEvent(type: string, data: { [key: string]: any }) {
    switch (type) {
        case "load":
            await registerPrefsScripts(data.window);
            break;
        default:
            return;
    }
}

async function onMainWindowUnload(win: Window): Promise<void> {
    // The toolkit is shared by all windows; only remove this window's menu.
    win.document.querySelector("#zotero-itemmenu-pdf2zh")?.remove();
    addon.data.dialog?.window?.close();
}

function onShutdown(): void {
    ztoolkit.unregisterAll();
    addon.data.dialog?.window?.close();
    // Remove addon object
    addon.data.alive = false;
    // @ts-ignore - Plugin instance is not typed
    delete Zotero[addon.data.config.addonInstance];
}

/**
 * This function is just an example of dispatcher for Notify events.
 * Any operations should be placed in a function to keep this funcion clear.
 */
async function onNotify(
    event: string,
    type: string,
    ids: Array<string | number>,
    extraData: { [key: string]: any },
) {
    return;
}

function onShortcuts(type: string) {
    switch (type) {
        default:
            break;
    }
}

async function onDialogEvents(type: string) {
    switch (type) {
        case "translatePDF":
            await processSelectedDocuments("translate", "both");
            break;
        case "translateMonoPDF":
            await processSelectedDocuments("translate", "mono");
            break;
        case "translateDualLRPDF":
            await processSelectedDocuments("translate", "dual-lr");
            break;
        case "cropPDF":
            await processSelectedDocuments("crop");
            break;
        case "crop-comparePDF":
            await processSelectedDocuments("crop-compare");
            break;
        case "comparePDF":
            await processSelectedDocuments("compare");
            break;
        default:
            break;
    }
}

export default {
    onStartup,
    onShutdown,
    onMainWindowLoad,
    onMainWindowUnload,
    onNotify,
    onPrefsEvent,
    onShortcuts,
    onDialogEvents,
};
