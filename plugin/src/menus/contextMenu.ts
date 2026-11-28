import { MenuitemOptions } from "zotero-plugin-toolkit";
import { getString } from "../utils/locale";
import type { TranslationMode } from "../translation/outputs";

export function registerContextMenu(win: Window) {
    // A string target resolves against the active window in the toolkit,
    // which may not be the window delivered by the lifecycle callback.
    const popup = win.document.querySelector<XUL.MenuPopup>("#zotero-itemmenu");
    if (!popup) {
        Zotero.logError(
            new Error(
                "[PDF2zh] Cannot register menu: #zotero-itemmenu is missing",
            ),
        );
        return;
    }
    if (win.document.querySelector("#zotero-itemmenu-pdf2zh")) return;
    const menuIcon = `chrome://${addon.data.config.addonRef}/content/icons/favicon@0.5x.svg`;
    const MENU_ITEMS: Array<{
        id: string;
        label: string;
        command: string;
    }> = [
        {
            id: "translate-pdf",
            label: getString("prefs-menu-translate"),
            command: "translatePDF",
        },
        {
            id: "translate-dual-lr-pdf",
            label: getString("prefs-menu-translate-dual-lr"),
            command: "translateDualLRPDF",
        },
        {
            id: "translate-mono-pdf",
            label: getString("prefs-menu-translate-mono"),
            command: "translateMonoPDF",
        },
    ];
    const pdf2zhMenu: MenuitemOptions = {
        tag: "menu",
        id: "zotero-itemmenu-pdf2zh",
        icon: menuIcon,
        label: `PDF2zh`,
        children: MENU_ITEMS.map(({ id, label, command }) => ({
            tag: "menuitem",
            id: `zotero-itemmenu-${id}`,
            label,
            commandListener: () => addon.hooks.onDialogEvents(command),
        })),
    };
    ztoolkit.Menu.register(popup, pdf2zhMenu);
    const menuRoot = win.document.querySelector<XUL.Menu>(
        "#zotero-itemmenu-pdf2zh",
    )!;
    patchMenuCompat(menuRoot, menuIcon);
}

const FALSE_BOOLEAN_ATTRS = ["hidden", "disabled", "checked"] as const;

/**
 * Post-registration compatibility fixes for generated menu nodes.
 *
 * 1. The toolkit writes hidden="false"/disabled="false"/checked="false" and
 *    type="" onto every node (Boolean(...) attributes are set verbatim).
 *    Zotero 11 (Firefox 153) judges boolean attributes by presence, not
 *    value, so literal "false" makes the whole menu invisible/disabled and
 *    every item render with a checkmark. Only the "false" value is
 *    stripped; a real hidden="true"/checked="true" is kept.
 * 2. Zotero 11 renders menu icons from the --menuitem-icon custom property
 *    (plus the *-iconic class); the toolkit's bare list-style-image no
 *    longer shows an icon, and on macOS it skips the class entirely.
 */
export function patchMenuCompat(
    root: Element | null | undefined,
    iconUrl: string | null,
): void {
    // Test doubles and exotic hosts may hand out plain objects; skip them.
    if (!root || typeof root.getAttribute !== "function") return;
    for (const attr of FALSE_BOOLEAN_ATTRS) {
        if (root.getAttribute(attr) === "false") {
            root.removeAttribute(attr);
        }
    }
    if (root.getAttribute("type") === "") {
        root.removeAttribute("type");
    }
    if (iconUrl) {
        // Only classic Gecko wiring here. Do NOT use Zotero 11's
        // zotero-custom-menu-item class: menuManager.js sweeps every
        // element bearing it that is not in Zotero's own registry
        // (`.CUSTOM_MENU_CLASS:not(.key)` -> remove()), which deletes our
        // whole menu at the first popup refresh.
        //
        // Icon plumbing differs by era and all of it is cheap to set:
        // - Zotero 7-10 (FF115 menu.js inheritedAttributes): the `image`
        //   attribute is inherited into the internal <image class="menu-icon">
        //   src; inline list-style-image is ignored by that path.
        // - Zotero 11 (FF153): CSS custom property / list-style-image.
        const tag = root.tagName?.toLowerCase() ?? "";
        root.setAttribute?.("image", iconUrl);
        root.classList?.add?.(
            tag === "menu" ? "menu-iconic" : "menuitem-iconic",
        );
        // Zotero's XUL Element typing omits `style`, but menu nodes expose it.
        const style = (root as { style?: CSSStyleDeclaration }).style;
        style?.setProperty?.("--menuitem-icon", `url("${iconUrl}")`);
        style?.setProperty?.("list-style-image", `url("${iconUrl}")`);
    }
    for (const child of Array.from(root.children ?? [])) {
        patchMenuCompat(child, null);
    }
}
