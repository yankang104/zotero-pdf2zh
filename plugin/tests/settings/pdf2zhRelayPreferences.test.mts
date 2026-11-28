import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const editorXhtml = fs.readFileSync(
    new URL(
        "../../addon/content/settings/api-editor/editor.xhtml",
        import.meta.url,
    ),
    "utf8",
);
const editorScript = fs.readFileSync(
    new URL(
        "../../addon/content/settings/api-editor/editor.js",
        import.meta.url,
    ),
    "utf8",
);
const preferencesXhtml = fs.readFileSync(
    new URL("../../addon/content/settings/preferences.xhtml", import.meta.url),
    "utf8",
);
const mainServiceDropdown = preferencesXhtml.match(
    /id="zotero-prefpane-__addonRef__-next_serviceSelect"[\s\S]*?<\/html:select>/,
)![0];
const builtInServices = Array.from(
    mainServiceDropdown.matchAll(
        /<html:option value="([^"]+)"\s*>([\s\S]*?)<\/html:option\s*>/g,
    ),
    ([, value, label]) => ({ value, label: label.trim() }),
);

function element(value = "", tagName = "input"): any {
    const node: any = {
        value,
        tagName: tagName.toUpperCase(),
        checked: false,
        textContent: "",
        style: {},
        dataset: {},
        children: [],
        listeners: new Map(),
        focused: false,
        classList: {
            toggle() {},
            add() {},
            remove() {},
        },
        focus() {
            node.focused = true;
        },
        addEventListener(event: string, listener: any) {
            node.listeners.set(event, listener);
        },
        dispatchEvent(event: Event) {
            node.listeners.get(event.type)?.({
                type: event.type,
                target: node,
            });
            return true;
        },
        appendChild(child: any) {
            child.parent = node;
            node.children.push(child);
            return child;
        },
        append(...children: any[]) {
            children.forEach((child) => node.appendChild(child));
        },
        replaceChildren(...children: any[]) {
            node.children = [];
            node.append(...children);
        },
        before() {},
        remove() {
            const parent = node.parent;
            if (parent) {
                parent.children = parent.children.filter(
                    (child: any) => child !== node,
                );
            }
        },
        cloneNode() {
            return element(node.value);
        },
    };
    Object.defineProperty(node, "options", {
        get: () => node.children,
    });
    Object.defineProperty(node, "firstChild", {
        get: () => node.children[0] ?? null,
    });
    Object.defineProperty(node, "label", {
        get: () => node.textContent,
    });
    node.removeChild = (child: any) => child.remove();
    return node;
}

function editor(
    values: Record<string, unknown> = {},
    onSave?: (data: any, useForTranslation: boolean) => any,
    currentConfiguration: Record<string, unknown> = {},
    windowArgs: Record<string, any> = {},
    preferenceStore?: any,
) {
    const nodes = new Map<string, any>();
    for (const id of [
        "service",
        "model",
        "apiKey",
        "apiUrl",
        "api-format-group",
        "relay-format",
        "relay-headers",
        "relay-body",
        "editor-save-status",
        "service-options",
        "model-options",
        "url-options",
        "dialog-title",
        "save-btn",
        "cancel-btn",
        "request-headers-fields",
        "request-headers-container",
        "model-actions",
        "fetch-models-status",
        "label-service-name",
        "label-api-key",
        "label-base-url",
        "label-api-format",
        "label-model",
        "label-relay-headers",
        "label-relay-body",
        "request-body-container",
        "native-request-settings-note",
    ]) {
        nodes.set(
            id,
            element(
                "",
                id.endsWith("-options") || id === "relay-format"
                    ? "select"
                    : "input",
            ),
        );
    }
    for (const format of ["chat", "responses", "messages"]) {
        nodes.get("relay-format").appendChild(element(format, "option"));
    }
    const rows = element();
    rows.getElementsByClassName = () => [];
    rows.querySelectorAll = () => [];
    nodes.set("extra-fields-container", rows);
    let closed = false;
    const args: any = {
        ...windowArgs,
        onSave,
        data: {
            ...currentConfiguration,
            extraData: values.extraData ?? currentConfiguration.extraData,
        },
        serviceCatalog: windowArgs.serviceCatalog ?? builtInServices,
        llmApiConfigs: windowArgs.llmApiConfigs ?? [],
    };
    const document = {
        documentElement: { lang: "zh-CN" },
        getElementById: (id: string) => nodes.get(id) ?? null,
        addEventListener() {},
        createElement: (tagName: string) => element("", tagName),
    };
    rows.ownerDocument = document;
    const context = vm.createContext({
        document,
        window: {
            arguments: [args],
            close() {
                closed = true;
            },
        },
        URL,
        Error,
        Event,
        Zotero: { Prefs: preferenceStore, locale: "zh-CN" },
        navigator: { language: "zh-CN" },
        alert: () => assert.fail("Unexpected modal alert"),
        confirm: () => false,
    });
    for (const file of ["presets", "parameters"]) {
        vm.runInContext(
            fs.readFileSync(
                new URL(
                    `../../addon/content/settings/api-editor/${file}.js`,
                    import.meta.url,
                ),
                "utf8",
            ),
            context,
        );
    }
    context.window.LlmApiEditorRequestHeaders = {
        initialize() {},
        getAuthMode: () => "auto",
        serializeHeaders: () => nodes.get("relay-headers").value,
        getHeaders: () => JSON.parse(nodes.get("relay-headers").value || "{}"),
        loadHeaders: (value: any) => {
            nodes.get("relay-headers").value =
                typeof value === "string" ? value : JSON.stringify(value || {});
        },
        refreshAutomaticHeaders() {},
    };
    context.window.LLMRequestBodyEditor = {
        create: () => ({
            template: "standard",
            setApiFormat() {},
            setManagedParameters() {},
            setService() {},
            load({ template, extraBody }: any) {
                this.template = template;
                nodes.get("relay-body").value =
                    typeof extraBody === "string"
                        ? extraBody
                        : JSON.stringify(extraBody);
            },
            collect() {
                return {
                    template: this.template,
                    extraBody: JSON.parse(
                        nodes.get("relay-body").value || "{}",
                    ),
                };
            },
        }),
    };
    context.window.LlmApiEditorModels = { initialize() {} };
    vm.runInContext(editorScript, context);
    context.window.LlmApiEditor.initialize();
    const initialService = nodes.get("service").value;
    if (values.service !== undefined) {
        const service = String(values.service);
        const builtin = builtInServices.find(
            ({ value }) => value === service.trim(),
        );
        const select = nodes.get("service-options");
        select.value = builtin?.value || "__custom_service__";
        select.dispatchEvent(new Event("change"));
        if (!builtin) {
            const input = nodes.get("service");
            input.value = service;
            input.dispatchEvent(new Event("input"));
            input.dispatchEvent(new Event("change"));
        }
    }
    for (const [id, value] of Object.entries(values)) {
        if (id === "service" || !nodes.has(id)) continue;
        nodes.get(id).value = value;
    }
    return {
        nodes,
        args,
        context,
        initialService,
        save: (use = false) => context.window.LlmApiEditor.save(use),
        closed: () => closed,
    };
}

function preferences(initial: any[] = []) {
    const prefs: Record<string, any> = {
        engine: "pdf2zh_next",
        service: "bing",
        next_service: "siliconflowfree",
        llmApis: JSON.stringify(initial),
    };
    let nextKey = 0;
    let failOnceAt = "";
    const nodes = new Map<string, any>();
    for (const id of [
        "engine",
        "next_serviceSelect",
        "llmapi-status",
        "llmapi-activate",
        "llmapi-remove",
    ]) {
        nodes.set(
            `zotero-prefpane-pdf2zh-${id}`,
            element("", id.endsWith("Select") ? "select" : "input"),
        );
    }
    const select = nodes.get("zotero-prefpane-pdf2zh-next_serviceSelect");
    for (const { value, label } of builtInServices) {
        const option = element(value, "option");
        option.textContent = label;
        select.appendChild(option);
    }
    const document: any = {
        getElementById: (id: string) => nodes.get(id) ?? null,
        createElement: (tagName: string) => element("", tagName),
        createElementNS: (_namespace: string, tagName: string) =>
            element("", tagName),
        querySelectorAll: () => [],
        querySelector: (selector: string) =>
            nodes.get(selector.slice(1)) ?? null,
    };
    const addon: any = {
        data: {
            prefs: {
                window: { document },
                tableHelper: {
                    treeInstance: {
                        invalidate() {},
                        selection: {
                            selected: [0],
                            select(index: number) {
                                this.selected = [index];
                            },
                        },
                    },
                },
            },
        },
    };
    let openedEditor: ReturnType<typeof editor>;
    let form: Record<string, unknown> = {};
    let use = false;
    let cancelIfFailed = false;
    let beforeSave: ((opened: ReturnType<typeof editor>) => void) | undefined;
    const context = vm.createContext({
        addon,
        URL,
        Error,
        setTimeout: (fn: any) => fn(),
        ztoolkit: { log() {} },
        Zotero: {
            locale: "zh-CN",
            Prefs: {
                get: (name: string) => prefs[name],
                set: (name: string, value: unknown) => {
                    prefs[name] = value;
                },
            },
            Utilities: { generateObjectKey: () => `NEW${++nextKey}` },
            Promise: {
                defer() {
                    let resolve: any;
                    const promise = new Promise((done) => {
                        resolve = done;
                    });
                    return { promise, resolve };
                },
            },
            getMainWindow: () => ({
                openDialog(_url: any, _name: any, _options: any, args: any) {
                    openedEditor = editor(
                        form,
                        args.onSave,
                        args.data,
                        args,
                        context.Zotero.Prefs,
                    );
                    beforeSave?.(openedEditor);
                    openedEditor.save(use);
                    Object.assign(args, openedEditor.args);
                    args._initPromise.resolve();
                    return {
                        get closed() {
                            return openedEditor.closed() || cancelIfFailed;
                        },
                    };
                },
            }),
        },
    });
    function load(file: string, imports: Record<string, any>) {
        const source = fs.readFileSync(new URL(file, import.meta.url), "utf8");
        const js = ts.transpileModule(source, {
            compilerOptions: {
                module: ts.ModuleKind.CommonJS,
                target: ts.ScriptTarget.ES2022,
            },
        }).outputText;
        const exports: any = {};
        vm.runInContext(
            `(function(require, exports) {${js}
            ${
                file.includes("preferenceScript")
                    ? "exports.openEditor = openLLMApiEditDialog; exports.bindEvents = bindPrefEvents;"
                    : ""
            }})`,
            context,
        )((name: string) => imports[name] ?? {}, exports);
        return exports;
    }
    const preferenceAccess = {
        getPref: (name: string) => prefs[name],
        setPref(name: string, value: unknown) {
            if (name === failOnceAt) {
                failOnceAt = "";
                throw new Error("Settings write failed");
            }
            prefs[name] = value;
        },
        clearPref: (name: string) => delete prefs[name],
    };
    const store = load("../../src/settings/apiConfigurations.ts", {
        "../utils/prefs": preferenceAccess,
    });
    store.reloadApiConfigurations();
    const texts = load("../../src/settings/preferences.ts", {});
    const tableModule = load("../../src/settings/apiTable.ts", {
        "../../package.json": { config: { addonRef: "pdf2zh" } },
        "../utils/prefs": preferenceAccess,
        "./apiConfigurations": store,
    });
    const table = tableModule.createApiTableController(
        addon.data.prefs.window,
        texts.prefText,
        () => {},
    );
    table.refresh();
    const actions = {
        openEditor: table.openEditor,
        bindEvents: table.bindEvents,
        getLLMServiceCatalog: table.getServiceCatalog,
        saveLLMApiConfiguration: table.save,
        loadLLMApisFromPrefs() {
            store.reloadApiConfigurations();
            table.refresh();
        },
    };
    return {
        addon,
        prefs,
        nodes,
        actions,
        store,
        fail: (name: string) => {
            failOnceAt = name;
        },
        async open(
            values: Record<string, unknown>,
            useForTranslation = false,
            cancelAfterFailure = false,
            editingKey?: string,
            interact?: (opened: ReturnType<typeof editor>) => void,
        ) {
            form = values;
            use = useForTranslation;
            cancelIfFailed = cancelAfterFailure;
            beforeSave = interact;
            const result = await actions.openEditor(editingKey);
            return { result, editor: openedEditor! };
        },
    };
}

const relay = {
    service: "my-relay",
    model: "test-model",
    apiUrl: "https://relay.example/v1",
    apiKey: "test-key",
    activate: false,
    extraData: { zotero_api_format: "responses" },
};

test("the native service selector shares the catalog and creates a Chinese provider without clearing connection settings", async () => {
    const settings = preferences();
    settings.prefs.next_service = "groq";
    const serviceCatalog = settings.actions.getLLMServiceCatalog();
    const ui = editor({}, undefined, {}, { serviceCatalog, llmApiConfigs: [] });
    assert.match(editorXhtml, /<select\s+id="service-options"/);
    assert.equal(builtInServices.length, 24);
    assert.deepEqual(
        Array.from(serviceCatalog, ({ value, label }: any) => ({
            value,
            label,
        })),
        builtInServices,
    );
    const select = ui.nodes.get("service-options");
    assert.equal(select.tagName, "SELECT");
    assert.equal(select.options[0].value, "");
    assert.equal(select.options[0].textContent, "▼");
    const customOption = select.options[1];
    assert.equal(customOption.value, "__custom_service__");
    assert.equal(customOption.textContent, "＋ 自定义服务商…");
    assert.deepEqual(
        select.options
            .filter(
                (option: any) =>
                    option.value && option.value !== customOption.value,
            )
            .map((option: any) => ({
                value: option.value,
                label: option.textContent,
            })),
        builtInServices,
    );
    select.value = "silicon";
    select.dispatchEvent(new Event("change"));
    assert.equal(ui.nodes.get("service").value, "SiliconFlow");
    assert.equal(ui.nodes.get("service").readOnly, true);
    assert.equal(ui.context.window.LlmApiEditor.getService(), "silicon");
    assert.equal(ui.nodes.get("apiUrl").value, "https://api.siliconflow.cn/v1");
    assert.equal(select.value, "");
    select.value = customOption.value;
    select.dispatchEvent(new Event("change"));
    assert.equal(ui.nodes.get("service").value, "");
    assert.equal(ui.nodes.get("service").readOnly, false);
    ui.nodes.get("service").value = "中";
    ui.nodes.get("service").dispatchEvent(new Event("input"));
    ui.nodes.get("service").dispatchEvent(new Event("change"));
    assert.equal(ui.nodes.get("service").value, "中");
    assert.equal(ui.context.window.LlmApiEditor.getService(), "中");
    const { result, editor: opened } = await settings.open(
        {
            ...relay,
            service: "groq",
            extraData: {
                ...relay.extraData,
                zotero_extra_headers: '{"X-Tenant":"research"}',
                zotero_extra_body: '{"store":false,"max_output_tokens":64}',
                zotero_body_template: "stream",
            },
        },
        true,
        false,
        undefined,
        (editing) => {
            const preservedFields = [
                "apiKey",
                "apiUrl",
                "model",
                "relay-format",
                "relay-headers",
                "relay-body",
            ];
            const before = preservedFields.map(
                (id) => editing.nodes.get(id).value,
            );
            const dropdown = editing.nodes.get("service-options");
            dropdown.value = customOption.value;
            dropdown.dispatchEvent(new Event("change"));
            assert.equal(editing.nodes.get("service").value, "");
            assert.equal(editing.nodes.get("service").focused, true);
            assert.equal(dropdown.value, "");
            assert.deepEqual(
                preservedFields.map((id) => editing.nodes.get(id).value),
                before,
            );
            editing.nodes.get("service").value = "中";
            editing.nodes.get("service").dispatchEvent(new Event("input"));
            editing.nodes.get("service").dispatchEvent(new Event("change"));
        },
    );
    assert.equal(result, true);
    assert.equal(opened.closed(), true);
    assert.equal(opened.initialService, "Groq");
    assert.equal(opened.args.data.service, "groq");
    assert.deepEqual(
        Array.from(opened.args.serviceCatalog, ({ value, label }: any) => ({
            value,
            label,
        })),
        builtInServices,
    );
    assert.equal(opened.args.llmApiConfigs.length, 0);
    const saved = JSON.parse(settings.prefs.llmApis)[0];
    assert.equal(saved.service, "中");
    assert.equal(saved.activate, true);
    assert.equal(saved.apiKey, relay.apiKey);
    assert.equal(saved.apiUrl, relay.apiUrl);
    assert.equal(saved.model, relay.model);
    assert.deepEqual(JSON.parse(saved.extraData.zotero_extra_headers), {
        "X-Tenant": "research",
    });
    assert.deepEqual(JSON.parse(saved.extraData.zotero_extra_body), {
        store: false,
        max_output_tokens: 64,
    });
    assert.equal(settings.prefs.engine, "pdf2zh_next");
    assert.equal(settings.prefs.next_service, "中");
    assert.equal(
        settings.nodes.get("zotero-prefpane-pdf2zh-next_serviceSelect").value,
        "中",
    );
    assert.equal(settings.store.getActiveApiConfiguration("中").key, saved.key);
    assert.equal(
        JSON.parse(settings.prefs.llmApis).some(
            (configuration: any) =>
                configuration.service === customOption.value,
        ),
        false,
    );
    assert.deepEqual(
        Array.from(
            settings.actions.getLLMServiceCatalog(),
            ({ value, label }: any) => ({
                value,
                label,
            }),
        ),
        [...builtInServices, { value: "中", label: "中（已配置）" }],
    );
    assert.deepEqual(
        settings.nodes
            .get("zotero-prefpane-pdf2zh-next_serviceSelect")
            .options.map((option: any) => ({
                value: option.value,
                label: option.textContent,
            })),
        [...builtInServices, { value: "中", label: "中（已配置）" }],
    );
});

test("ordinary save stores trimmed relay values and advertises it without switching", async () => {
    const ui = preferences();
    const { result } = await ui.open({
        ...relay,
        service: " my-relay ",
        model: " test-model ",
        apiUrl: " https://relay.example/v1 ",
        apiKey: " test-key ",
    });
    assert.equal(result, true);
    const saved = JSON.parse(ui.prefs.llmApis)[0];
    assert.equal(saved.service, relay.service);
    assert.equal(saved.model, relay.model);
    assert.equal(saved.apiUrl, relay.apiUrl);
    assert.equal(saved.apiKey, relay.apiKey);
    assert.equal(saved.activate, false);
    assert.equal(ui.prefs.engine, "pdf2zh_next");
    assert.equal(ui.prefs.next_service, "siliconflowfree");
    const options = ui.nodes.get(
        "zotero-prefpane-pdf2zh-next_serviceSelect",
    ).options;
    assert.equal(
        options.filter((option: any) => option.value === "my-relay").length,
        1,
    );
    assert.match(
        ui.nodes.get("zotero-prefpane-pdf2zh-llmapi-status").textContent,
        /已保存.*未激活.*尚未选/,
    );
});

test("save and use activates one configuration and updates engine, service and controls", async () => {
    const old = { ...relay, key: "OLD", activate: true };
    const ui = preferences([old]);
    await ui.open(relay, true);
    const entries = JSON.parse(ui.prefs.llmApis);
    assert.equal(
        entries.find((entry: any) => entry.key === "OLD").activate,
        false,
    );
    assert.equal(entries.filter((entry: any) => entry.activate).length, 1);
    assert.equal(ui.prefs.engine, "pdf2zh_next");
    assert.equal(ui.prefs.next_service, "my-relay");
    assert.equal(
        ui.nodes.get("zotero-prefpane-pdf2zh-next_serviceSelect").value,
        "my-relay",
    );
    assert.deepEqual(
        ui.addon.data.prefs.tableHelper.treeInstance.selection.selected,
        [entries.findIndex((entry: any) => entry.key !== "OLD")],
    );
    assert.equal(ui.store.getApiConfiguration("OLD").activate, false);

    assert.match(
        ui.nodes.get("zotero-prefpane-pdf2zh-llmapi-status").textContent,
        /已保存.*已激活.*当前翻译/,
    );
});

test("switching a saved Chat configuration to Responses survives reload and reopening with its template and request fields", async () => {
    const existing = {
        ...relay,
        key: "EXISTING",
        activate: true,
        extraData: {
            zotero_api_format: "chat",
            zotero_body_template: "minimal",
            zotero_extra_headers: '{"X-Tenant":"demo"}',
            zotero_extra_body: '{"store":false,"max_output_tokens":64}',
        },
    };
    const ui = preferences([existing]);
    const { result } = await ui.open(
        {},
        true,
        false,
        existing.key,
        (opened) => {
            assert.equal(opened.nodes.get("api-format-group").hidden, false);
            const format = opened.nodes.get("relay-format");
            assert.equal(format.value, "chat");
            format.value = "responses";
            format.dispatchEvent(new Event("change"));
        },
    );
    assert.equal(result, true);
    ui.actions.loadLLMApisFromPrefs();
    const active = ui.store.getActiveApiConfiguration(existing.service);
    assert.equal(active.key, existing.key);
    assert.equal(ui.prefs.next_service, existing.service);
    assert.equal(active.extraData.zotero_api_format, "responses");
    assert.equal(active.extraData.zotero_body_template, "minimal");
    assert.deepEqual(
        JSON.parse(active.extraData.zotero_extra_headers),
        JSON.parse(existing.extraData.zotero_extra_headers),
    );
    assert.deepEqual(
        JSON.parse(active.extraData.zotero_extra_body),
        JSON.parse(existing.extraData.zotero_extra_body),
    );

    const { editor: reopened } = await ui.open({}, false, false, existing.key);
    assert.equal(reopened.nodes.get("relay-format").value, "responses");
    assert.equal(reopened.nodes.get("api-format-group").hidden, false);
    assert.equal(reopened.args.data.extraData.zotero_body_template, "minimal");
    assert.equal(JSON.parse(ui.prefs.llmApis).length, 1);
});

test("renaming the selected service keeps its configuration key and follows the new dropdown name", async () => {
    const ui = preferences([{ ...relay, key: "OLD", activate: true }]);
    ui.prefs.engine = "pdf2zh_next";
    ui.prefs.next_service = relay.service;
    ui.prefs["extensions.pdf2zh.llm.history"] = JSON.stringify({
        [relay.service]: { models: ["historic-model"], urls: [relay.apiUrl] },
        "deleted-provider": { models: ["deleted-model"], urls: [relay.apiUrl] },
    });
    const { editor: originalEditor } = await ui.open(
        { ...relay, service: "我的", activate: true },
        false,
        false,
        "OLD",
    );
    assert.equal(originalEditor.initialService, relay.service);
    assert.equal(originalEditor.args.llmApiConfigs[0].key, "OLD");
    const entries = JSON.parse(ui.prefs.llmApis);
    assert.equal(entries.length, 1);
    assert.equal(entries[0].key, "OLD");
    assert.equal(entries[0].service, "我的");
    assert.equal(ui.prefs.next_service, "我的");
    assert.equal(ui.prefs.engine, "pdf2zh_next");
    const select = ui.nodes.get("zotero-prefpane-pdf2zh-next_serviceSelect");
    assert.equal(select.value, "我的");
    assert.equal(
        select.options.some((option: any) => option.value === relay.service),
        false,
    );
    assert.equal(ui.store.getApiConfiguration("OLD").service, "我的");

    const { editor: reopened } = await ui.open({}, false, false, "OLD");
    assert.equal(reopened.initialService, "我的");
    assert.equal(reopened.args.data.service, "我的");
    assert.deepEqual(
        reopened.nodes
            .get("service-options")
            .options.filter(
                (option: any) =>
                    option.value && option.value !== "__custom_service__",
            )
            .map((option: any) => ({
                value: option.value,
                label: option.textContent,
            })),
        [...builtInServices, { value: "我的", label: "我的（已配置）" }],
    );
    assert.deepEqual(
        Array.from(reopened.args.serviceCatalog, ({ value, label }: any) => ({
            value,
            label,
        })),
        [...builtInServices, { value: "我的", label: "我的（已配置）" }],
    );
    assert.equal(
        reopened.nodes
            .get("service-options")
            .options.some(
                (option: any) =>
                    option.value === relay.service ||
                    option.value === "deleted-provider",
            ),
        false,
    );
});

test("failed settings writes roll back storage and do not deactivate the existing configuration", () => {
    const old = { ...relay, key: "OLD", activate: true };
    const ui = preferences([old]);
    const before = { ...ui.prefs };
    ui.fail("engine");
    assert.throws(
        () => ui.actions.saveLLMApiConfiguration(relay, undefined, true),
        /Settings write failed/,
    );
    assert.deepEqual(ui.prefs, before);
    assert.equal(ui.store.listApiConfigurations().length, 1);

    assert.equal(ui.store.listApiConfigurations().length, 1);
    assert.equal(ui.store.getApiConfiguration("OLD").activate, true);
    const invalid = editor(relay, () => ({
        success: false,
        message: "Settings write failed",
    }));
    invalid.save(true);
    assert.equal(invalid.closed(), false);
    assert.match(
        invalid.nodes.get("editor-save-status").textContent,
        /Settings write failed/,
    );
    assert.equal(invalid.nodes.get("apiUrl").value, relay.apiUrl);
    assert.equal(invalid.args.result, undefined);
});

test("deleting and reloading configurations keeps stale history out of the service catalog", async () => {
    const ui = preferences([{ ...relay, key: "OLD", activate: true }]);
    ui.prefs["extensions.pdf2zh.llm.history"] = JSON.stringify({
        [relay.service]: { models: ["historic-model"], urls: [relay.apiUrl] },
    });
    ui.actions.bindEvents();
    ui.nodes
        .get("zotero-prefpane-pdf2zh-llmapi-remove")
        .listeners.get("command")();
    assert.equal(ui.store.listApiConfigurations().length, 0);
    assert.equal(ui.store.listApiConfigurations().length, 0);
    assert.deepEqual(
        Array.from(
            ui.actions.getLLMServiceCatalog(),
            ({ value, label }: any) => ({
                value,
                label,
            }),
        ),
        builtInServices,
    );
    ui.prefs.llmApis = "[]";
    ui.actions.loadLLMApisFromPrefs();
    assert.equal(ui.store.listApiConfigurations().length, 0);
    assert.equal(ui.store.listApiConfigurations().length, 0);
    assert.equal(
        ui.nodes
            .get("zotero-prefpane-pdf2zh-next_serviceSelect")
            .options.some((option: any) => option.value === "my-relay"),
        false,
    );
    const { editor: reopened } = await ui.open({});
    assert.equal(reopened.initialService, "SiliconFlow Free");
    assert.equal(
        reopened.nodes
            .get("service-options")
            .options.some((option: any) => option.value === relay.service),
        false,
    );
    assert.equal(reopened.args.llmApiConfigs.length, 0);
});

test("actual editor save callback reports storage failure without closing or publishing the new config", async () => {
    const ui = preferences();
    const before = ui.prefs.llmApis;
    ui.fail("llmApis");
    const { result, editor: opened } = await ui.open(relay, false, true);
    assert.equal(result, false);
    assert.equal(opened.closed(), false);
    assert.match(
        opened.nodes.get("editor-save-status").textContent,
        /保存失败/,
    );
    assert.match(
        ui.nodes.get("zotero-prefpane-pdf2zh-llmapi-status").textContent,
        /保存失败/,
    );
    assert.equal(opened.nodes.get("apiUrl").value, relay.apiUrl);
    assert.equal(ui.prefs.llmApis, before);
    assert.equal(ui.store.listApiConfigurations().length, 0);
});

test("activation event and manual dropdown selection keep stored and runtime state consistent", () => {
    const old = { ...relay, key: "OLD", activate: true };
    const inactive = { ...relay, key: "SECOND", activate: false };
    const ui = preferences([old, inactive]);
    ui.addon.data.prefs.tableHelper.treeInstance.selection.selected = [1];
    ui.actions.bindEvents();
    const activate = ui.nodes.get("zotero-prefpane-pdf2zh-llmapi-activate");
    activate.listeners.get("command")();
    const entries = JSON.parse(ui.prefs.llmApis);
    assert.equal(entries.find((api: any) => api.key === "OLD").activate, false);
    assert.equal(
        entries.find((api: any) => api.key === "SECOND").activate,
        true,
    );
    assert.equal(ui.store.getApiConfiguration("OLD").activate, false);

    assert.equal(ui.prefs.next_service, "siliconflowfree");
    const select = ui.nodes.get("zotero-prefpane-pdf2zh-next_serviceSelect");
    select.value = "my-relay";
    select.listeners.get("change")({ target: select });
    assert.equal(ui.prefs.next_service, "my-relay");
    assert.equal(ui.prefs.engine, "pdf2zh_next");
    assert.match(
        ui.nodes.get("zotero-prefpane-pdf2zh-llmapi-status").textContent,
        /PDF2zh Next.*my-relay.*已激活/,
    );
});

test("loading duplicate active configurations persists the same winner used by translation", () => {
    const ui = preferences([
        { ...relay, key: "FIRST", activate: true },
        { ...relay, key: "SECOND", activate: true },
    ]);
    const entries = JSON.parse(ui.prefs.llmApis);
    assert.equal(entries.filter((api: any) => api.activate).length, 1);
    assert.equal(
        entries.find((api: any) => api.key === "SECOND").activate,
        true,
    );
    assert.equal(ui.store.getApiConfiguration("FIRST").activate, false);
});
