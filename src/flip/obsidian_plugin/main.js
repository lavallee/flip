/* flip — Obsidian companion for flip notebooks (SPEC §12).
 *
 * A thin metadata surface over the flip CLI's --json commands: doctor
 * findings and the hot view in a right-sidebar panel, a status bar summary,
 * and open-by-id navigation. The plugin never writes notebook files; every
 * fact on screen comes from `flip doctor --json`, `flip show --json`, and
 * the list commands, run at the vault root.
 *
 * Workspace vaults (SPEC §18): a vault root carrying .flip/workspace.toml
 * holds many notebooks. Doctor runs workspace-wide (`--workspace`), the
 * open-by-id modal aggregates every bound notebook's ids under their
 * handle-qualified form (recipes:A3), and the hot view stays per-notebook.
 *
 * Plain CommonJS on purpose: Obsidian loads manifest.json + main.js
 * directly, so there is no build step and no dependencies beyond the
 * Obsidian API and node's child_process (isDesktopOnly).
 */

"use strict";

const { Plugin, ItemView, PluginSettingTab, Setting, Notice, SuggestModal } = require("obsidian");
const { execFile } = require("child_process");

const VIEW_TYPE = "flip-doctor";
const WORKSPACE_TABLE_PATH = ".flip/workspace.toml";

const DEFAULT_SETTINGS = {
  flipPath: "flip",
  autoRefresh: true,
};

const BEAT_GUIDANCE =
  "This vault is a flip beat root. Doctor and the hot view work at notebook " +
  "roots — open a notebook inside this beat (notebooks/<slug>/) as its own vault.";

const NOT_A_ROOT_GUIDANCE =
  "This vault is not a flip notebook root (no index.md with flip: frontmatter) " +
  "or workspace root (no .flip/workspace.toml). Run `flip obsidian` inside a " +
  "notebook and open that folder as a vault, or `flip ws init` at a shared root.";

function isError(finding) {
  return Boolean(finding) && String(finding.level || "").toUpperCase() === "ERROR";
}

function isWarn(finding) {
  return Boolean(finding) && String(finding.level || "").toUpperCase() === "WARN";
}

function firstLine(text) {
  return String(text || "").split("\n")[0].trim();
}

// ---------------------------------------------------------------- sidebar view

class FlipDoctorView extends ItemView {
  constructor(leaf, plugin) {
    super(leaf);
    this.plugin = plugin;
  }

  getViewType() {
    return VIEW_TYPE;
  }

  getDisplayText() {
    return "flip";
  }

  getIcon() {
    return "stethoscope";
  }

  async onOpen() {
    this.render();
    this.plugin.refresh();
  }

  render() {
    const state = this.plugin.state || {};
    const root = this.contentEl;
    root.empty();
    root.addClass("flip-view");

    const header = root.createDiv({ cls: "flip-header" });
    header.createEl("h4", { text: "flip", cls: "flip-title" });
    if (state.kind === "workspace") {
      header.createSpan({ cls: "flip-badge flip-badge-status", text: "workspace" });
    }
    const refresh = header.createEl("button", { text: "Refresh", cls: "flip-refresh" });
    refresh.setAttribute("aria-label", "Refresh doctor & hot view");
    refresh.addEventListener("click", () => this.plugin.refresh());

    const doctor = root.createDiv({ cls: "flip-section" });
    doctor.createDiv({ cls: "flip-section-title", text: "Doctor" });

    if (state.error) {
      doctor.createDiv({ cls: "flip-empty", text: String(state.error) });
      return;
    }
    if (state.kind === "beat") {
      doctor.createDiv({ cls: "flip-empty", text: BEAT_GUIDANCE });
      return;
    }
    if (state.kind === "workspace") {
      this.renderFindings(doctor, Array.isArray(state.findings) ? state.findings : []);
      const hot = root.createDiv({ cls: "flip-section" });
      hot.createDiv({ cls: "flip-section-title", text: "Hot view" });
      hot.createDiv({
        cls: "flip-empty",
        text: "per-notebook — open a bound notebook as its own vault",
      });
      return;
    }
    if (state.kind !== "notebook") {
      doctor.createDiv({ cls: "flip-empty", text: NOT_A_ROOT_GUIDANCE });
      return;
    }

    this.renderFindings(doctor, Array.isArray(state.findings) ? state.findings : []);
    this.renderHot(root, state.hot && typeof state.hot === "object" ? state.hot : {});
  }

  renderFindings(section, findings) {
    const errors = findings.filter(isError);
    const warns = findings.filter(isWarn);
    const rest = findings.filter((f) => f && !isError(f) && !isWarn(f));
    const ordered = errors.concat(warns, rest);
    if (!ordered.length) {
      section.createDiv({ cls: "flip-empty", text: "ok: no findings" });
      return;
    }
    for (const finding of ordered) this.renderFinding(section, finding);
  }

  renderFinding(section, finding) {
    const level = String((finding && finding.level) || "WARN").toUpperCase();
    const row = section.createDiv({ cls: "flip-row" });
    row.createSpan({
      cls: "flip-badge " + (level === "ERROR" ? "flip-badge-error" : "flip-badge-warn"),
      text: level,
    });
    row.createSpan({ cls: "flip-code", text: String((finding && finding.code) || "") });
    row.createSpan({ cls: "flip-text", text: String((finding && finding.message) || "") });
    const path = finding && typeof finding.path === "string" ? finding.path : "";
    if (path) {
      row.addClass("flip-row-clickable");
      row.setAttribute("title", path);
      row.addEventListener("click", () => this.plugin.openVaultPath(path));
    }
  }

  renderHot(root, hot) {
    const section = root.createDiv({ cls: "flip-section" });
    section.createDiv({ cls: "flip-section-title", text: "Hot view" });

    const questions = Array.isArray(hot.open_questions) ? hot.open_questions : [];
    const claims = Array.isArray(hot.claims_needing_work) ? hot.claims_needing_work : [];

    section.createDiv({ cls: "flip-subtitle", text: "Open questions" });
    if (!questions.length) section.createDiv({ cls: "flip-empty", text: "none" });
    for (const q of questions) {
      if (!q || typeof q !== "object") continue;
      const row = section.createDiv({ cls: "flip-row" });
      row.createSpan({ cls: "flip-id", text: String(q.id || "") });
      row.createSpan({ cls: "flip-text", text: String(q.text || "") });
      this.makeIdRowClickable(row, q.id);
    }

    section.createDiv({ cls: "flip-subtitle", text: "Claims needing work" });
    if (!claims.length) section.createDiv({ cls: "flip-empty", text: "none" });
    for (const c of claims) {
      if (!c || typeof c !== "object") continue;
      const row = section.createDiv({ cls: "flip-row" });
      row.createSpan({ cls: "flip-id", text: String(c.id || "") });
      row.createSpan({ cls: "flip-badge flip-badge-status", text: String(c.status || "?") });
      if (c.load_bearing) {
        row.createSpan({ cls: "flip-badge flip-badge-load", text: "load-bearing" });
      }
      row.createSpan({ cls: "flip-text", text: String(c.description || "") });
      this.makeIdRowClickable(row, c.id);
    }
  }

  makeIdRowClickable(row, id) {
    const clean = String(id || "").trim();
    if (!clean) return;
    row.addClass("flip-row-clickable");
    row.setAttribute("title", "flip open " + clean);
    row.addEventListener("click", () => {
      this.plugin.openById(clean).catch((e) => new Notice(firstLine(e && e.message) || "flip open failed"));
    });
  }
}

// ---------------------------------------------------------------- open-by-id modal

class FlipIdModal extends SuggestModal {
  constructor(plugin, kind) {
    super(plugin.app);
    this.plugin = plugin;
    this.kind = kind || "notebook";
    this.items = [];
    this.loaded = false;
    this.setPlaceholder(
      this.kind === "workspace"
        ? "Open by id — type recipes:A3, A3, Q1… or search titles"
        : "Open by id — type A3, C7, Q1… or search titles"
    );
  }

  onOpen() {
    super.onOpen();
    this.loadItems();
  }

  async loadItems() {
    // One root in a notebook vault; every bound notebook in a workspace
    // vault, with ids surfaced in their handle-qualified form (recipes:A3)
    // so `flip open` gets an unambiguous ref back.
    const base = this.plugin.basePath();
    let roots = [{ cwd: null, handle: null }];
    if (this.kind === "workspace") {
      const table = await this.plugin.readWorkspaceTable();
      roots = table.map((nb) => ({ cwd: base + "/" + nb.path, handle: nb.handle }));
    }
    const jsonOrEmpty = (args, cwd) => this.plugin.flipJson(args, cwd).catch(() => []);
    const perRoot = await Promise.all(
      roots.map((root) =>
        Promise.all([
          jsonOrEmpty(["source", "list", "--json"], root.cwd),
          jsonOrEmpty(["claim", "list", "--json"], root.cwd),
          jsonOrEmpty(["question", "list", "--json"], root.cwd),
        ])
      )
    );
    const items = [];
    for (let i = 0; i < roots.length; i++) {
      const handle = roots[i].handle;
      for (const rows of perRoot[i]) {
        if (!Array.isArray(rows)) continue;
        for (const row of rows) {
          if (!row || typeof row !== "object" || !row.id) continue;
          items.push({
            id: handle ? handle + ":" + String(row.id) : String(row.id),
            label:
              String(row.title || row.description || row.text || row.slug || "") +
              (handle ? " · " + handle : ""),
          });
        }
      }
    }
    this.items = items;
    this.loaded = true;
    // Re-run the current query so freshly loaded ids show without a keystroke.
    if (this.inputEl) this.inputEl.dispatchEvent(new Event("input"));
  }

  getSuggestions(query) {
    const q = String(query || "").trim().toLowerCase();
    const matches = this.items.filter(
      (it) => !q || it.id.toLowerCase().includes(q) || it.label.toLowerCase().includes(q)
    );
    // Free-typed refs (D2, TH3, recipes:A3…) work even when not in the
    // loaded lists; a deprecated "#" separator is normalized to ":".
    const m = q.match(/^(?:([a-z][a-z0-9-]*)[:#])?([a-z]+\d+)$/);
    if (m) {
      const ref = (m[1] ? m[1] + ":" : "") + m[2].toUpperCase();
      if (!this.items.some((it) => it.id.toLowerCase() === ref.toLowerCase())) {
        matches.unshift({ id: ref, label: "open this id", free: true });
      }
    }
    return matches;
  }

  renderSuggestion(item, el) {
    el.addClass("flip-suggestion");
    el.createDiv({ cls: "flip-suggestion-id", text: item.id });
    if (item.label) el.createDiv({ cls: "flip-suggestion-label", text: item.label });
  }

  onChooseSuggestion(item) {
    this.plugin
      .openById(item.id)
      .catch((e) => new Notice(firstLine(e && e.message) || "flip open failed"));
  }
}

// ---------------------------------------------------------------- settings tab

class FlipSettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }

  display() {
    const { containerEl } = this;
    containerEl.empty();

    new Setting(containerEl)
      .setName("flip path")
      .setDesc(
        'Path to the flip binary. The default "flip" resolves on PATH; set an ' +
          "absolute path (see `which flip`) if Obsidian cannot find it."
      )
      .addText((text) =>
        text
          .setPlaceholder("flip")
          .setValue(this.plugin.settings.flipPath)
          .onChange(async (value) => {
            this.plugin.settings.flipPath = value.trim() || "flip";
            await this.plugin.saveSettings();
          })
      );

    new Setting(containerEl)
      .setName("Auto-refresh")
      .setDesc(
        "Refresh doctor and the hot view shortly after vault files change " +
          "(only while the flip panel is open)."
      )
      .addToggle((toggle) =>
        toggle.setValue(this.plugin.settings.autoRefresh).onChange(async (value) => {
          this.plugin.settings.autoRefresh = value;
          await this.plugin.saveSettings();
        })
      );
  }
}

// ---------------------------------------------------------------- plugin

class FlipPlugin extends Plugin {
  async onload() {
    await this.loadSettings();
    this.state = { kind: null, findings: [], hot: null, error: null };
    this.refreshTimer = null;

    this.registerView(VIEW_TYPE, (leaf) => new FlipDoctorView(leaf, this));
    this.addRibbonIcon("stethoscope", "flip: open doctor & hot view", () => this.activateView());

    this.statusBarEl = this.addStatusBarItem();
    this.statusBarEl.addClass("flip-status", "mod-clickable");
    this.statusBarEl.setAttribute("aria-label", "flip: open doctor & hot view");
    this.statusBarEl.addEventListener("click", () => this.activateView());
    this.updateStatusBar();

    this.addCommand({
      id: "open-panel",
      name: "Open doctor & hot view panel",
      callback: () => this.activateView(),
    });
    this.addCommand({
      id: "refresh",
      name: "Refresh doctor & hot view",
      callback: () => this.refresh(),
    });
    this.addCommand({
      id: "open-by-id",
      name: "Open by id",
      callback: async () => {
        const kind = await this.rootKind();
        if (kind === "beat") {
          new Notice(
            "flip open works at a notebook root — open a notebook inside this " +
              "beat (notebooks/<slug>/) as its own vault"
          );
          return;
        }
        if (kind !== "notebook" && kind !== "workspace") {
          new Notice(NOT_A_ROOT_GUIDANCE);
          return;
        }
        new FlipIdModal(this, kind).open();
      },
    });

    this.addSettingTab(new FlipSettingTab(this.app, this));
    this.registerEvent(this.app.vault.on("modify", () => this.scheduleRefresh()));
    this.app.workspace.onLayoutReady(() => this.refresh());
  }

  onunload() {
    if (this.refreshTimer) clearTimeout(this.refreshTimer);
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }

  async saveSettings() {
    await this.saveData(this.settings);
  }

  // -------------------------------------------------------------- vault plumbing

  basePath() {
    // Local filesystem vaults only (FileSystemAdapter); sync/mobile adapters
    // have no base path and cannot host a child process anyway.
    const adapter = this.app.vault.adapter;
    if (!adapter || typeof adapter.getBasePath !== "function") return null;
    return adapter.getBasePath();
  }

  async rootKind() {
    // Same cheap sniffs flip itself uses for root discovery. A workspace
    // root carries .flip/workspace.toml (SPEC §18) — checked first, since a
    // workspace root is never also a notebook root. Otherwise the vault
    // root's index.md opens a frontmatter block declaring flip: (notebook)
    // or flip_beat: (beat). No parse — doctor does the strict validation.
    try {
      await this.app.vault.adapter.read(WORKSPACE_TABLE_PATH);
      return "workspace";
    } catch (e) {
      // not a workspace root; fall through to the index.md sniff
    }
    try {
      const text = await this.app.vault.adapter.read("index.md");
      const head = String(text).slice(0, 4096);
      if (!head.startsWith("---\n")) return "none";
      const lines = head.split("\n---")[0].split("\n");
      if (lines.some((line) => line.startsWith("flip:"))) return "notebook";
      if (lines.some((line) => line.startsWith("flip_beat:"))) return "beat";
      return "none";
    } catch (e) {
      return "none";
    }
  }

  async readWorkspaceTable() {
    // Minimal TOML-subset reader for the [notebooks] table flip writes:
    // [section] headers plus `handle = "path"` lines whose RHS is a basic
    // string (flip serializes paths with json.dumps, so JSON.parse reads
    // them back exactly). Hand-edited files that stray outside this subset
    // get a Notice and an empty table — doctor owns the real diagnosis.
    let text;
    try {
      text = await this.app.vault.adapter.read(WORKSPACE_TABLE_PATH);
    } catch (e) {
      return [];
    }
    const notebooks = [];
    let section = null;
    for (const raw of String(text).split("\n")) {
      const line = raw.trim();
      if (!line || line.startsWith("#")) continue;
      const header = line.match(/^\[([^\]]*)\]$/);
      if (header) {
        section = header[1].trim();
        continue;
      }
      if (section !== "notebooks") continue;
      const eq = line.indexOf("=");
      let path = null;
      const handle = eq > 0 ? line.slice(0, eq).trim() : "";
      try {
        path = eq > 0 ? JSON.parse(line.slice(eq + 1).trim()) : null;
      } catch (e) {
        path = null;
      }
      if (typeof path !== "string" || !/^[a-z][a-z0-9-]*$/.test(handle)) {
        new Notice(
          WORKSPACE_TABLE_PATH + " has an entry this plugin cannot read — " +
            "run `flip doctor --workspace` for the full story"
        );
        return [];
      }
      notebooks.push({ handle: handle, path: path });
    }
    return notebooks;
  }

  execFlip(args, cwd) {
    // cwd defaults to the vault root; workspace vaults pass a bound
    // notebook's directory so per-notebook commands run where flip expects.
    return new Promise((resolve, reject) => {
      const base = this.basePath();
      if (!base) {
        reject(new Error("flip needs a vault on the local filesystem"));
        return;
      }
      const bin = String(this.settings.flipPath || "flip").trim() || "flip";
      const opts = { cwd: cwd || base, maxBuffer: 32 * 1024 * 1024 };
      execFile(bin, args, opts, (err, stdout, stderr) => {
        if (err && (err.code === "ENOENT" || err.code === "EACCES")) {
          const friendly = new Error(
            'flip binary not found ("' + bin + '") — set "flip path" in Settings → flip'
          );
          friendly.notFound = true;
          reject(friendly);
          return;
        }
        // Non-zero exit is not fatal here: `flip doctor --json` exits 1 when
        // it has ERROR findings but still prints the JSON we came for.
        resolve({ err, stdout: String(stdout || ""), stderr: String(stderr || "") });
      });
    });
  }

  async flipJson(args, cwd) {
    const { err, stdout, stderr } = await this.execFlip(args, cwd);
    try {
      return JSON.parse(stdout);
    } catch (e) {
      const detail = firstLine(stderr) || (err ? firstLine(err.message) : "");
      throw new Error("flip " + args.join(" ") + " failed" + (detail ? ": " + detail : ""));
    }
  }

  toVaultRelative(absPath) {
    const base = this.basePath();
    if (!base) return null;
    const norm = (s) => String(s).replace(/\\/g, "/").replace(/\/+$/, "");
    const nb = norm(base);
    const np = norm(absPath);
    if (np === nb) return "";
    if (np.startsWith(nb + "/")) return np.slice(nb.length + 1);
    return null;
  }

  openVaultPath(path) {
    const clean = String(path || "").replace(/^\.\//, "");
    if (!clean) return;
    this.app.workspace.openLinkText(clean, "", false);
  }

  async openById(id) {
    const clean = String(id || "").trim();
    if (!clean) return;
    const { err, stdout, stderr } = await this.execFlip(["open", clean]);
    const out = firstLine(stdout);
    if (err || !out) {
      new Notice(firstLine(stderr) || "flip open " + clean + " failed");
      return;
    }
    const rel = this.toVaultRelative(out);
    if (rel === null) {
      new Notice("flip open " + clean + ": " + out + " is outside this vault");
      return;
    }
    this.openVaultPath(rel);
  }

  // -------------------------------------------------------------- refresh

  scheduleRefresh() {
    if (!this.settings.autoRefresh) return;
    if (!this.app.workspace.getLeavesOfType(VIEW_TYPE).length) return;
    if (this.refreshTimer) clearTimeout(this.refreshTimer);
    this.refreshTimer = setTimeout(() => {
      this.refreshTimer = null;
      this.refresh();
    }, 2500);
  }

  async refresh() {
    const state = { kind: null, findings: [], hot: null, error: null };
    if (!this.basePath()) {
      state.kind = "none";
      state.error = "flip needs a vault on the local filesystem";
    } else {
      state.kind = await this.rootKind();
      if (state.kind === "notebook") {
        try {
          const [findings, hot] = await Promise.all([
            this.flipJson(["doctor", "--json"]),
            this.flipJson(["show", "--json"]),
          ]);
          state.findings = Array.isArray(findings) ? findings : [];
          state.hot = hot && typeof hot === "object" ? hot : {};
        } catch (e) {
          state.error = firstLine(e && e.message) || "flip failed";
          if (e && e.notFound) new Notice(state.error);
        }
      } else if (state.kind === "workspace") {
        // Workspace-wide lint; the hot view stays per-notebook (open a
        // bound notebook as its own vault for it).
        try {
          const findings = await this.flipJson(["doctor", "--workspace", "--json"]);
          state.findings = Array.isArray(findings) ? findings : [];
        } catch (e) {
          state.error = firstLine(e && e.message) || "flip failed";
          if (e && e.notFound) new Notice(state.error);
        }
      }
    }
    this.state = state;
    this.updateStatusBar();
    for (const leaf of this.app.workspace.getLeavesOfType(VIEW_TYPE)) {
      if (leaf.view && typeof leaf.view.render === "function") leaf.view.render();
    }
  }

  updateStatusBar() {
    if (!this.statusBarEl) return;
    const state = this.state || {};
    let text = "flip: —";
    if (state.kind === "notebook" && !state.error) {
      const findings = Array.isArray(state.findings) ? state.findings : [];
      const errs = findings.filter(isError).length;
      const warns = findings.filter(isWarn).length;
      const claims =
        state.hot && Array.isArray(state.hot.claims_needing_work)
          ? state.hot.claims_needing_work.length
          : 0;
      text = "flip: " + errs + "❗ " + warns + "⚠ · " + claims + " claims open";
    } else if (state.kind === "workspace" && !state.error) {
      const findings = Array.isArray(state.findings) ? state.findings : [];
      text = "flip: workspace · " + findings.filter(isError).length + "❗ " +
        findings.filter(isWarn).length + "⚠";
    } else if (state.kind === "beat") {
      text = "flip: beat root";
    }
    this.statusBarEl.setText(text);
  }

  async activateView() {
    const existing = this.app.workspace.getLeavesOfType(VIEW_TYPE);
    if (existing.length) {
      this.app.workspace.revealLeaf(existing[0]);
      return;
    }
    const leaf = this.app.workspace.getRightLeaf(false);
    if (!leaf) return;
    await leaf.setViewState({ type: VIEW_TYPE, active: true });
    this.app.workspace.revealLeaf(leaf);
    this.refresh();
  }
}

module.exports = FlipPlugin;
