import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";

function modelHelpers(initialConfig: Record<string, unknown>) {
    const nodes = new Map<string, any>();
    const requests: Array<{ method: string; url: string; options: any }> = [];
    const updates: Array<{
        service: string;
        models: string[];
        selected: string;
    }> = [];
    let currentConfig = initialConfig;
    let requestModelList: () => Promise<any> = async () => ({
        status: 200,
        responseText: JSON.stringify({
            data: [{ id: "model-a" }, { id: "model-b" }],
        }),
    });
    function element(): any {
        const node: any = {
            value: "",
            children: [],
            listeners: new Map(),
            classList: { toggle() {}, add() {} },
            append(...children: any[]) {
                node.children.push(...children);
            },
            appendChild(child: any) {
                node.children.push(child);
                return child;
            },
            addEventListener(event: string, listener: any) {
                node.listeners.set(event, listener);
            },
            setAttribute() {},
        };
        Object.defineProperty(node, "id", {
            set(value: string) {
                nodes.set(value, node);
            },
        });
        return node;
    }
    const modelGroup = element();
    for (const id of ["model", "service", "apiUrl"]) {
        nodes.set(id, element());
    }
    nodes.get("model").closest = () => modelGroup;
    nodes.get("model").value = "hand-entered-model";
    const context = vm.createContext({
        document: {
            documentElement: { lang: "en" },
            head: element(),
            getElementById: (id: string) => nodes.get(id),
            createElement: element,
            addEventListener() {},
        },
        window: {},
        URL,
        Zotero: {
            HTTP: {
                request: async (method: string, url: string, options: any) => {
                    requests.push({ method, url, options });
                    return requestModelList();
                },
            },
        },
    });
    for (const file of ["presets.js", "requestHeaders.js", "models.js"]) {
        vm.runInContext(
            fs.readFileSync(
                new URL(
                    `../../addon/content/settings/api-editor/${file}`,
                    import.meta.url,
                ),
                "utf8",
            ),
            context,
        );
    }
    const modules = (context as any).window;
    modules.LlmApiEditorModels.initialize({
        getCurrentConfig: () => currentConfig,
        getModel: () => nodes.get("model").value,
        updateModels: (service: string, models: string[], selected: string) => {
            updates.push({ service, models, selected });
        },
        http: (context as any).Zotero.HTTP,
        t: (key: string, ...args: any[]) => {
            const value = modules.LlmApiEditorPresets.UI_TEXT.en[key];
            return typeof value === "function" ? value(...args) : value;
        },
    });
    return {
        nodes,
        requests,
        updates,
        headers: modules.LlmApiEditorRequestHeaders,
        fetchModels: () =>
            nodes.get("fetch-models-btn").listeners.get("click")(),
        setConfig: (config: Record<string, unknown>) => {
            currentConfig = config;
        },
        setRequest: (handler: () => Promise<any>) => {
            requestModelList = handler;
        },
    };
}

test("model lists directly GET the provider with the current headers and report request failures", async () => {
    const configuration = {
        service: "my-relay",
        apiUrl: "https://relay.invalid/v1/messages",
        apiKey: "offline-key",
        model: "hand-entered-model",
        extraData: {
            zotero_api_format: "messages",
            zotero_auth_mode: "auto",
            zotero_extra_headers: {
                "User-Agent": "offline-client",
                "x-api-key": null,
            },
        },
    };
    const helpers = modelHelpers(configuration);
    const headers = helpers.headers.buildRequestHeaders(
        "messages",
        "offline-key",
        configuration.extraData.zotero_extra_headers,
    );
    assert.equal(headers["User-Agent"], "offline-client");
    assert.equal(headers["anthropic-version"], "2023-06-01");
    assert.equal(Object.hasOwn(headers, "x-api-key"), false);
    const responses = helpers.headers.buildRequestHeaders(
        "responses",
        "offline-key",
        { authorization: "custom-token" },
    );
    assert.equal(responses.authorization, "custom-token");
    assert.equal(Object.hasOwn(responses, "Authorization"), false);
    await helpers.fetchModels();
    assert.equal(helpers.requests[0].url, "https://relay.invalid/v1/models");
    assert.equal(helpers.requests[0].method, "GET");
    assert.equal(helpers.requests[0].options.timeout, 20000);
    assert.equal(
        helpers.requests[0].options.headers["User-Agent"],
        "offline-client",
    );
    assert.equal(
        helpers.requests[0].options.headers["anthropic-version"],
        "2023-06-01",
    );
    assert.equal(
        Object.hasOwn(helpers.requests[0].options.headers, "x-api-key"),
        false,
    );
    assert.equal(helpers.requests[0].options.body, undefined);

    for (const status of [401, 403, 404]) {
        helpers.setRequest(async () => {
            throw Object.assign(
                new Error("private response with offline-key"),
                { status },
            );
        });
        await helpers.fetchModels();
        const message = helpers.nodes.get("fetch-models-status").textContent;
        assert.match(message, new RegExp(`HTTP ${status}`));
        assert.doesNotMatch(message, /private|offline-key/);
    }
    helpers.setRequest(async () => ({
        status: 200,
        responseText: "<html>private</html>",
    }));
    await helpers.fetchModels();
    assert.match(
        helpers.nodes.get("fetch-models-status").textContent,
        /did not return JSON/,
    );
    helpers.setRequest(async () => {
        throw new Error("Request timed out after 20000 ms");
    });
    await helpers.fetchModels();
    assert.match(
        helpers.nodes.get("fetch-models-status").textContent,
        /20 seconds/,
    );
    assert.equal(helpers.nodes.get("fetch-models-btn").disabled, false);
});

test("fetched model candidates keep the hand-entered model and follow configuration changes", async () => {
    const helpers = modelHelpers({
        service: "my-relay",
        apiUrl: "https://relay.invalid/v1",
    });
    await helpers.fetchModels();
    assert.equal(helpers.nodes.get("model").value, "hand-entered-model");
    assert.equal(helpers.updates[0].selected, "hand-entered-model");
    assert.deepEqual(Array.from(helpers.updates[0].models), [
        "model-a",
        "model-b",
    ]);
    helpers.setConfig({
        service: "deepseek",
        apiUrl: "https://api.deepseek.com",
    });
    helpers.nodes.get("model").value = "current-deepseek-model";
    await helpers.fetchModels();
    assert.equal(helpers.requests[1].url, "https://api.deepseek.com/models");
    assert.equal(helpers.updates[1].service, "deepseek");
    assert.equal(helpers.updates[1].selected, "current-deepseek-model");
    assert.equal(helpers.nodes.get("model").value, "current-deepseek-model");
    assert.equal(helpers.nodes.get("fetch-models-btn").disabled, false);

    let completeRequest: (response: any) => void = () => {};
    helpers.setRequest(
        () =>
            new Promise((resolve) => {
                completeRequest = resolve;
            }),
    );
    const pending = helpers.fetchModels();
    helpers.setConfig({
        service: "new-provider",
        apiUrl: "https://new.invalid/v1",
    });
    helpers.nodes.get("model").value = "new-provider-model";
    helpers.nodes.get("service").listeners.get("input")();
    completeRequest({
        status: 200,
        responseText: '{"data":[{"id":"old-provider-model"}]}',
    });
    await pending;
    assert.equal(helpers.updates[2].service, "deepseek");
    assert.equal(helpers.updates[2].selected, "current-deepseek-model");
    assert.equal(helpers.nodes.get("model").value, "new-provider-model");
    assert.equal(helpers.nodes.get("fetch-models-status").textContent, "");

    const requestCount = helpers.requests.length;
    helpers.setConfig({ service: "bing", apiUrl: "" });
    await helpers.fetchModels();
    assert.equal(helpers.requests.length, requestCount);
    assert.match(
        helpers.nodes.get("fetch-models-status").textContent,
        /no model-list endpoint/,
    );
});
