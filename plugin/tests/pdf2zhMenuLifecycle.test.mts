import assert from "node:assert/strict";
import test from "node:test";
import fs from "node:fs";
import vm from "node:vm";
import ts from "typescript";
import { supportsTranslationMode } from "../src/modules/pdf2zhTranslationOutputs.ts";

// Execute the production hooks/menu factory with a small DOM/toolkit double.
// The double models toolkit 5.1.0-beta.10: string targets use the active
// document, unregisterAll removes every node owned by that instance, and
// generated nodes carry hidden="false"/disabled="false" attributes.
function fakeMenuNode(options: any, popup?: any, key?: string) {
    const node: any = {
        options,
        attrs: {
            hidden: "false",
            disabled: "false",
            checked: "false",
            type: "",
        },
        styles: {},
        classes: new Set<string>(),
        children: [] as any[],
        listeners: new Map<string, () => void>(),
        addEventListener(name: string, listener: () => void) {
            node.listeners.set(name, listener);
        },
        querySelector(selector: string): any {
            for (const child of node.children) {
                if (`#${child.options.id}` === selector) return child;
                const match = child.querySelector(selector);
                if (match) return match;
            }
            return null;
        },
        getAttribute(name: string) {
            return name in node.attrs ? node.attrs[name] : null;
        },
        removeAttribute(name: string) {
            delete node.attrs[name];
        },
        setAttribute(name: string, value: string) {
            node.attrs[name] = value;
        },
        get tagName() {
            return options?.tag ?? "menuitem";
        },
        get classList() {
            return {
                add: (cls: string) => node.classes.add(cls),
                contains: (cls: string) => node.classes.has(cls),
            };
        },
        get style() {
            return {
                setProperty: (k: string, v: string) => {
                    node.styles[k] = v;
                },
                getPropertyValue: (k: string) => node.styles[k] ?? "",
            };
        },
    };
    for (const child of options?.children ?? []) {
        node.children.push(fakeMenuNode(child));
    }
    if (popup && key) {
        node.remove = () => {
            if (popup.nodes.get(key) === node) popup.nodes.delete(key);
        };
    }
    return node;
}
function setup() {
    const windows: any[] = [];
    const errors: any[] = [];
    const commands: string[] = [];
    const selectedItems: any[] = [];
    const tasks: any[] = [];
    const preferences: Record<string, unknown> = {
        engine: "pdf2zh_next",
        babeldoc: false,
    };
    let active: any;
    function window() {
        const nodes = new Map();
        const doc: any = {
            querySelector: (selector: string) => nodes.get(selector) ?? null,
        };
        const popup = { ownerDocument: doc, nodes };
        nodes.set("#zotero-itemmenu", popup);
        const win = { document: doc, nodes, popup };
        windows.push(win);
        active = win;
        return win;
    }
    function createZToolkit() {
        const owned: any[] = [];
        return {
            getGlobal(name: string) {
                if (name === "ZoteroPane") {
                    return { getSelectedItems: () => selectedItems };
                }
            },
            Menu: {
                register(target: any, options: any) {
                    const popup =
                        typeof target === "string"
                            ? active.document.querySelector("#zotero-itemmenu")
                            : target;
                    if (!popup) return false;
                    const key = `#${options.id}`;
                    // Mirrors toolkit 5.1.0-beta.10: every generated menu
                    // node carries hidden="false"/disabled="false" because
                    // Boolean(...) attributes are set verbatim.
                    const node = fakeMenuNode(options, popup, key);
                    owned.push(node);
                    popup.nodes.set(key, node);
                },
            },
            unregisterAll() {
                owned.forEach((node) => node.remove());
            },
        };
    }
    const addon: any = {
        data: {
            alive: true,
            config: { addonRef: "pdf2zh" },
            ztoolkit: createZToolkit(),
        },
        hooks: { onDialogEvents: (command: string) => commands.push(command) },
    };
    const context: any = vm.createContext({
        addon,
        rootURI: "test/",
        Zotero: {
            getMainWindows: () => windows,
            getMainWindow: () => active,
            Promise: { delay: async () => {} },
            PreferencePanes: { register() {} },
            logError: (error: any) => errors.push(error),
        },
    });
    Object.defineProperty(context, "ztoolkit", {
        get: () => addon.data.ztoolkit,
    });
    function load(path: string, imports: any) {
        const source = fs.readFileSync(new URL(path, import.meta.url), "utf8");
        const js = ts.transpileModule(source, {
            compilerOptions: {
                module: ts.ModuleKind.CommonJS,
                target: ts.ScriptTarget.ES2022,
            },
        }).outputText;
        const exports = {};
        const run = vm.runInContext(
            `(function(require, exports) {${js}\n})`,
            context,
        );
        run((name: string) => imports[name] ?? {}, exports);
        return exports as any;
    }
    const locale = { getString: (key: string) => key, initLocale() {} };
    const factory = load("../src/modules/pdf2zh.ts", {
        "../utils/locale": locale,
        "../utils/prefs": { getPref: (key: string) => preferences[key] },
        "./pdf2zhTranslationOutputs": { supportsTranslationMode },
    });
    const hooks = load("../src/hooks.ts", {
        "./modules/pdf2zh": factory,
        "./modules/pdf2zhHelper": {
            PDF2zhHelperFactory: {
                processWorker: async (...args: any[]) => tasks.push(args),
            },
        },
        "./utils/locale": locale,
        "./utils/ztoolkit": { createZToolkit },
        "./modules/preferenceScript": { initTableUI() {} },
    }).default;
    const menu = (win: any) => win.nodes.get("#zotero-itemmenu-pdf2zh");
    return {
        window,
        hooks,
        addon,
        menu,
        errors,
        commands,
        factory,
        selectedItems,
        tasks,
        preferences,
    };
}

test("translation commands submit their mode directly without opening a dialog", async () => {
    const s = setup();
    const win: any = s.window();
    win.openDialog = () => {
        assert.fail("translation menu must not open an output dialog");
    };
    await s.hooks.onDialogEvents("translateMonoPDF");
    await s.hooks.onDialogEvents("translateDualLRPDF");
    await s.hooks.onDialogEvents("translateDualTBPDF");
    assert.deepEqual(
        s.tasks.map((task) => Array.from(task)),
        [
            ["translate", "mono"],
            ["translate", "dual-lr"],
            ["translate", "dual-tb"],
        ],
    );
});

test("native translation menu offers only the three supported output actions", async () => {
    const s = setup();
    const win = s.window();
    await s.hooks.onMainWindowLoad(win);
    const menu = s.menu(win);
    assert.equal(menu.children.length, 3);
    for (const child of menu.children) {
        assert.equal(child.options.tag, "menuitem");
        assert.ok(!child.options.label.startsWith("PDF2zh:"));
        assert.equal(child.getAttribute("type"), null);
        assert.equal(child.getAttribute("checked"), null);
        assert.equal(child.getAttribute("disabled"), null);
    }
    s.preferences.engine = "pdf2zh";
    s.preferences.babeldoc = false;
    menu.listeners.get("popupshowing")?.();
    assert.equal(menu.children[0].getAttribute("disabled"), null);
    assert.equal(menu.children[1].getAttribute("disabled"), "true");
    assert.equal(menu.children[2].getAttribute("disabled"), null);
    s.preferences.engine = "pdf2zh_next";
    menu.listeners.get("popupshowing")?.();
    assert.equal(menu.children[1].getAttribute("disabled"), null);
});

test("startup registers each window even when another window is active", async () => {
    const s = setup();
    const a = s.window();
    const b = s.window();
    await s.hooks.onStartup();
    assert.ok(s.menu(a));
    assert.ok(s.menu(b));
});
test("closing an older window leaves the newer window menu usable", async () => {
    const s = setup();
    const a = s.window();
    await s.hooks.onMainWindowLoad(a);
    const b = s.window();
    await s.hooks.onMainWindowLoad(b);
    await s.hooks.onMainWindowUnload(a);
    assert.ok(s.menu(b));
    assert.equal(s.menu(a), undefined);
    for (const item of s.menu(b).options.children) item.commandListener();
    assert.deepEqual(s.commands, [
        "translateMonoPDF",
        "translateDualLRPDF",
        "translateDualTBPDF",
    ]);
});
test("shutdown removes menus from every window, then reload registers them", async () => {
    const s = setup();
    const a = s.window();
    await s.hooks.onMainWindowLoad(a);
    const b = s.window();
    await s.hooks.onMainWindowLoad(b);
    s.hooks.onShutdown();
    assert.equal(s.menu(a), undefined);
    assert.equal(s.menu(b), undefined);
    s.addon.data.alive = true;
    await s.hooks.onStartup();
    assert.ok(s.menu(a));
    assert.ok(s.menu(b));
});
test("repeated load does not replace or duplicate a menu", async () => {
    const s = setup();
    const a = s.window();
    await s.hooks.onMainWindowLoad(a);
    const original = s.menu(a);
    await s.hooks.onMainWindowLoad(a);
    assert.equal(s.menu(a), original);
});
test("missing popup is diagnosed and a later load can retry", async () => {
    const s = setup();
    const a = s.window();
    a.nodes.delete("#zotero-itemmenu");
    await s.hooks.onMainWindowLoad(a);
    assert.equal(s.menu(a), undefined);
    assert.equal(s.errors.length, 1);
    a.nodes.set("#zotero-itemmenu", a.popup);
    await s.hooks.onMainWindowLoad(a);
    assert.ok(s.menu(a));
});
test("toolkit-style false boolean attributes are stripped after registration", async () => {
    // Zotero 11 (Firefox 153) hides/disables by attribute presence, so the
    // toolkit's hidden="false"/disabled="false" must not survive.
    const s = setup();
    const a = s.window();
    await s.hooks.onMainWindowLoad(a);
    const node = s.menu(a);
    assert.ok(node);
    assert.equal(node.getAttribute("hidden"), null);
    assert.equal(node.getAttribute("disabled"), null);
    assert.ok(node.children.length > 0);
    for (const child of node.children) {
        assert.equal(child.getAttribute("hidden"), null);
        assert.equal(child.getAttribute("disabled"), null);
        assert.equal(child.getAttribute("checked"), null);
        assert.equal(child.getAttribute("type"), null);
    }
});
test("menu root gains Zotero 11 icon wiring after registration", async () => {
    // Classic Gecko wiring only: --menuitem-icon + list-style-image and
    // the *-iconic class. The zotero-custom-menu-item class must NOT be
    // used — Zotero 11's menuManager removes unregistered elements that
    // bear it, deleting our whole menu at the first popup refresh.
    // Only the root menu carries the logo — per-item icons read as
    // checkmarks in the cramped 16px slot.
    const s = setup();
    const a = s.window();
    await s.hooks.onMainWindowLoad(a);
    const node = s.menu(a);
    const nodeIconUrl = `chrome://${s.addon.data.config.addonRef}/content/icons/favicon@0.5x.svg`;
    assert.ok(node);
    assert.ok(node.classList.contains("menu-iconic"));
    assert.ok(!node.classList.contains("zotero-custom-menu-item"));
    assert.equal(node.getAttribute("image"), nodeIconUrl);
    assert.equal(node.styles["--custom-menu-icon-light"], undefined);
    assert.match(node.styles["--menuitem-icon"], /favicon@0\.5x\.svg/);
    assert.match(node.styles["list-style-image"], /favicon@0\.5x\.svg/);
    assert.ok(node.children.length > 0);
    for (const child of node.children) {
        assert.ok(!child.classList.contains("menuitem-iconic"));
        assert.equal(child.styles["--menuitem-icon"], undefined);
        assert.ok(!child.classList.contains("zotero-custom-menu-item"));
    }
});
test("patchMenuCompat keeps real hidden=true and skips non-DOM nodes", () => {
    const s = setup();
    const patch = s.factory.patchMenuCompat as (el: any, icon: string) => void;
    const root: any = {
        attrs: {
            hidden: "false",
            disabled: "false",
            checked: "false",
            type: "",
        },
        children: [
            { attrs: { hidden: "true" }, children: [] },
            {
                attrs: { hidden: "false", disabled: "false" },
                children: [],
                getAttribute(name: string) {
                    return name in this.attrs ? this.attrs[name] : null;
                },
                removeAttribute(name: string) {
                    delete this.attrs[name];
                },
            },
        ],
        getAttribute(name: string) {
            return name in this.attrs ? this.attrs[name] : null;
        },
        removeAttribute(name: string) {
            delete this.attrs[name];
        },
    };
    patch(root, "icon.svg");
    assert.equal(root.getAttribute("hidden"), null);
    assert.equal(root.getAttribute("disabled"), null);
    assert.equal(root.getAttribute("checked"), null);
    assert.equal(root.getAttribute("type"), null);
    assert.equal(root.children[0].attrs.hidden, "true");
    assert.equal(root.children[1].getAttribute("hidden"), null);
    assert.equal(root.children[1].getAttribute("disabled"), null);
    // Plain objects without DOM accessors must be tolerated, not throw.
    patch({ children: [{ attrs: {} }] }, "icon.svg");
    patch(undefined, "icon.svg");
    patch(null, "icon.svg");
});
