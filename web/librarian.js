import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

function fmt(bytes) {
    if (!bytes) return "0 GB";
    return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}

async function refresh(bar) {
    const cfg = await (await api.fetchApi("/librarian/config", { cache: "no-store" })).json();
    bar.querySelector(".lib-enabled").checked = cfg.enabled;
    bar.querySelector(".lib-dir").value = cfg.parent_dir;
    bar.querySelector(".lib-quota").value = cfg.quota_gb;
    bar.querySelector(".lib-status").textContent = `${fmt(cfg.used)} / ${cfg.quota_gb} GB · ${cfg.cache_dir}`;
}

function makeBar() {
    const bar = document.createElement("div");
    bar.id = "comfy-librarian-bar";
    bar.innerHTML = `
        <b>Librarian</b>
        <label><input class="lib-enabled" type="checkbox"> enabled</label>
        <span>parent</span><input class="lib-dir" placeholder="cache parent directory">
        <span>quota GB</span><input class="lib-quota" type="number" min="1" step="1">
        <button class="lib-save">save</button>
        <span class="lib-status">loading…</span>`;

    bar.querySelector(".lib-save").onclick = async () => {
        const body = JSON.stringify({
            enabled: bar.querySelector(".lib-enabled").checked,
            parent_dir: bar.querySelector(".lib-dir").value,
            quota_gb: bar.querySelector(".lib-quota").value,
        });
        await api.fetchApi("/librarian/config", { method: "POST", body, headers: { "Content-Type": "application/json" } });
        refresh(bar);
    };
    document.body.appendChild(bar);
    refresh(bar);
    setInterval(() => refresh(bar), 10000);
}

app.registerExtension({
    name: "ComfyUI.Librarian",
    async setup() {
        if (!document.getElementById("comfy-librarian-css")) {
            const link = document.createElement("link");
            link.id = "comfy-librarian-css";
            link.rel = "stylesheet";
            link.href = new URL("librarian.css", import.meta.url).href;
            document.head.appendChild(link);
        }
        if (!document.getElementById("comfy-librarian-bar")) makeBar();
    },
});
