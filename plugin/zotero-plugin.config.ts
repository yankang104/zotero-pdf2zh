import { defineConfig } from "zotero-plugin-scaffold";
import pkg from "./package.json";

export default defineConfig({
    source: ["src", "addon"],
    dist: "build",
    name: pkg.config.addonName,
    id: pkg.config.addonID,
    namespace: pkg.config.addonRef,
    updateURL: `https://raw.githubusercontent.com/{{owner}}/{{repo}}/refs/heads/zotero-updates/${
        pkg.version.includes("-") ? "update-beta.json" : "update.json"
    }`,
    xpiDownloadLink:
        "https://github.com/{{owner}}/{{repo}}/releases/download/v{{version}}/{{xpiName}}.xpi",

    build: {
        assets: ["addon/**/*.*"],
        define: {
            ...pkg.config,
            author: pkg.author,
            description: pkg.description,
            homepage: pkg.homepage,
            buildVersion: pkg.version,
            buildTime: "{{buildTime}}",
        },
        esbuildOptions: [
            {
                entryPoints: ["src/index.ts"],
                define: {
                    __env__: `"${process.env.NODE_ENV}"`,
                },
                bundle: true,
                target: "firefox115",
                outfile: `build/addon/content/scripts/${pkg.config.addonRef}.js`,
            },
        ],
    },

    // Tagged CI publishes the canonical root artifacts and update manifests.
    // Local release keeps the scaffold's version/tag workflow.
    release: {
        github: { enable: false },
    },

    // If you need to see a more detailed log, uncomment the following line:
    // logLevel: "trace",
});
