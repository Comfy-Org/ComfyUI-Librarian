import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { ComfyDialog } from "../../scripts/ui.js";

function fmt(bytes) {
    return `${((bytes || 0) / 1024 ** 3).toFixed(1)} GB`;
}

class LibrarianDialog extends ComfyDialog {
    constructor() {
        super();
        this.element.classList.add("comfy-librarian-dialog");
        this.parentDir = "";
    }

    async show() {
        this.cfg = await (await api.fetchApi("/librarian/config", { cache: "no-store" })).json();
        this.parentDir = this.cfg.parent_dir || "";
        this.content = document.createElement("div");
        this.content.className = "comfy-librarian-config";
        this.content.innerHTML = `
            <h2>ComfyUI-Librarian Settings</h2>
            <p class="lib-instructions">Please configure a cache location, this should be a writable location on a drive faster than your model library.</p>
            <label><input class="lib-enabled" type="checkbox"> Enable cache</label>
            <label>Cache parent directory</label>
            <div class="lib-path-row"><span class="lib-path"></span><button type="button" class="lib-browse">Browse…</button></div>
            <label>Max Cache Size: <input class="lib-quota" type="number" min="1" step="1"> GB</label>
            <div class="lib-status"></div>
            <label><input class="lib-startup" type="checkbox"> Disable Startup Check</label>`;
        this.content.querySelector(".lib-enabled").checked = this.cfg.enabled;
        this.content.querySelector(".lib-quota").value = this.cfg.quota_gb;
        this.content.querySelector(".lib-startup").checked = this.cfg.startup_check_disabled;
        this.renderPath();
        this.renderInstructions();
        this.renderStatus();
        this.content.querySelector(".lib-enabled").onchange = () => this.save();
        this.content.querySelector(".lib-quota").oninput = () => this.save();
        this.content.querySelector(".lib-startup").onchange = () => this.save();
        this.content.querySelector(".lib-browse").onclick = async () => {
            const result = await (await api.fetchApi("/librarian/browse", { method: "POST" })).json();
            const parentDir = result.parent_dir;
            if (!parentDir) {
                this.content.querySelector(".lib-status").textContent = "No directory was selected.";
                return;
            }
            this.parentDir = parentDir;
            this.renderPath();
            this.save();
        };
        super.show(this.content);
    }

    renderPath() {
        this.content.querySelector(".lib-path").textContent = this.parentDir || "No directory selected";
    }

    renderInstructions() {
        const text = this.parentDir
            ? "cache directory configured ✅"
            : "Please configure a cache location, this should be a writable location on a drive faster than your model library.";
        this.content.querySelector(".lib-instructions").textContent = text;
    }

    renderStatus() {
        const text = this.parentDir
            ? `${fmt(this.cfg.used)} used · cache ${this.cfg.cache_dir}`
            : "";
        this.content.querySelector(".lib-status").textContent = text;
    }

    async save() {
        const body = JSON.stringify({
            enabled: this.content.querySelector(".lib-enabled").checked,
            parent_dir: this.parentDir,
            quota_gb: this.content.querySelector(".lib-quota").value,
            startup_check_disabled: this.content.querySelector(".lib-startup").checked,
        });
        this.cfg = await (await api.fetchApi("/librarian/config", { method: "POST", body, headers: { "Content-Type": "application/json" } })).json();
        this.parentDir = this.cfg.parent_dir || "";
        this.renderPath();
        this.renderInstructions();
        this.renderStatus();
    }

    createButtons() {
        return [Object.assign(document.createElement("button"), { type: "button", textContent: "Close", onclick: () => this.close() })];
    }
}

const dialog = new LibrarianDialog();

app.registerExtension({
    name: "ComfyUI.Librarian",
    commands: [{ id: "Librarian.Configure", label: "Configure Librarian", menubarLabel: "Configure", function: () => dialog.show() }],
    menuCommands: [{ path: ["Librarian"], commands: ["Librarian.Configure"] }],
    async setup() {
        if (!document.getElementById("comfy-librarian-css")) {
            const link = document.createElement("link");
            link.id = "comfy-librarian-css";
            link.rel = "stylesheet";
            link.href = new URL("librarian.css", import.meta.url).href;
            document.head.appendChild(link);
        }
        const cfg = await (await api.fetchApi("/librarian/config", { cache: "no-store" })).json();
        if (!cfg.configured && !cfg.startup_check_disabled) setTimeout(() => dialog.show(), 500);
    },
});
