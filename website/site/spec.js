/* The spec map: the bundle as a navigation surface into SPEC.md.

   The structure of the directory listing is authored here (it is presentation).
   Everything factual — entity types, the frontmatter keys each page really
   carries, ledgers, lifecycle, profiles, the CLI surface, and the section
   anchors — comes from data/spec.js and data/flip.js, generated at build time
   and cross-checked against a notebook the build actually created. */
(function () {
  "use strict";

  var spec = window.__FLIP_SPEC__;
  var meta = window.__FLIP_META__;
  var kit = window.flipsite;
  if (!spec || !kit) return;

  var SPEC_URL = "https://github.com/lavallee/flip/blob/main/SPEC.md";

  // Frontmatter keys OKF itself defines. Everything else is flip's extension
  // vocabulary — the part an OKF consumer must preserve and may ignore.
  var OKF_CORE = ["type", "title", "description", "resource", "tags", "timestamp"];

  function entity(type) {
    return spec.entities.filter(function (e) { return e.type === type; })[0];
  }

  // -- the bundle listing ---------------------------------------------------
  var LAYOUT = [
    { path: "index.md", note: "bundle root: the manifest", detail: { kind: "section", spec: "4",
      title: "The manifest",
      body: "OKF sanctions frontmatter on exactly one index, the bundle root — so that "
        + "is where notebook identity lives: slug, uid, title, kind, status, "
        + "visibility, and the policy keys that govern what may leave. The body below "
        + "it is a generated directory listing; hand edits to the body do not survive, "
        + "while frontmatter keys flip does not know are preserved on rewrite." } },
    { path: "notebook.md", note: "the prose heart: working memory", detail: { kind: "section", spec: "13",
      title: "notebook.md",
      body: "Working memory, scaffolded by profile into a section menu: the tip, the "
        + "frame, the answer banded honestly as direct / adjacent / unresolved, the "
        + "assessment where confidence, coverage and usefulness are never collapsed, "
        + "hypotheses with named falsifiers, gaps and self-critique. Sections graduate "
        + "to their own files when they outgrow a heading." } },
    { path: "log.md", note: "generated view of the work log", detail: { kind: "section", spec: "8",
      title: "log.md",
      body: "An OKF reserved file and a disposable projection: the newest-first "
        + "rendering of log/log.jsonl, regenerated on every mutating command. Never "
        + "edit it; edit the notebook and re-generate." } },
    { dir: "references/", note: "one page per source", detail: { kind: "entity", type: "Source" } },
    { dir: "claims/", note: "one page per assertion", detail: { kind: "entity", type: "Claim" } },
    { dir: "decisions/", note: "resolved forks, and why", detail: { kind: "entity", type: "Decision" } },
    { dir: "questions/", note: "what still needs answering", detail: { kind: "entity", type: "Question" } },
    { dir: "sessions/", note: "one page per working episode", detail: { kind: "entity", type: "Work Session" } },
    { dir: "analysis/", note: "graduated prose", detail: { kind: "section", spec: "3",
      title: "analysis/",
      body: "Where a notebook.md section goes once it outgrows a heading: "
        + "hypotheses.md, findings.md, and whatever else the work needs. Concept "
        + "pages, so any type fits." } },
    { dir: "sources/", note: "custody", children: [
        { dir: "raw/", note: "verbatim bytes as captured" },
        { dir: "text/", note: "readable derivatives, 1:1 by id, written by flip extract" },
        { path: "_provenance.jsonl", note: "append-only capture log" }
      ], detail: { kind: "section", spec: "5",
      title: "sources/ — custody",
      body: "Verbatim bytes as captured, never edited and never re-encoded; one file "
        + "or one directory per source. Recapture creates a new dated entry rather "
        + "than overwriting. Beside them, the capture log records url, local path, "
        + "sha256, byte count, tool, version, strategy and actor — one line per "
        + "acquisition, appended and never rewritten. This is the fixity record, and "
        + "it is what flip export bag turns into a real BagIt bag." } },
    { dir: "derived/", note: "reprocessable outputs", children: [
        { path: "_derivations.jsonl", note: "append-only processing log" }
      ], detail: { kind: "section", spec: "8",
      title: "derived/",
      body: "Anything produced from sources by a recorded process — parsed tables, "
        + "transcripts, extractions. The derivation log records inputs to tool and "
        + "parameters to outputs, with hashes: a deliberately small PROV profile, so "
        + "that OCR or an extraction can be re-run and re-assessed rather than "
        + "trusted." } },
    { dir: "log/", note: "event ledgers", children: [
        { path: "log.jsonl", note: "the work log" },
        { path: "passed.jsonl", note: "negative evidence" }
      ], detail: { kind: "section", spec: "8",
      title: "log/",
      body: "Two append-only ledgers. The work log is what happened: fetched X, ran Y, "
        + "hit wall Z. The passed ledger is what was considered and rejected, with the "
        + "reason — negative evidence, so the next session does not rediscover and "
        + "re-chase the same dead end." } },
    { dir: "drafts/", note: "v0/, v1/, current →", detail: { kind: "section", spec: "11",
      title: "drafts/",
      body: "Versioned explicitly, each version carrying a changelog naming what "
        + "changed and which finding or decision drove it." } },
    { dir: "renders/", note: "generated artifacts (gitignored by default)", detail: { kind: "section", spec: "11",
      title: "renders/",
      body: "Renderers are pure — same notebook in, same render out — and they write "
        + "only here. Renders are never edited: a fix flows back to the notebook and "
        + "you re-render. This site is one." } },
    { path: "HANDOFF.md", note: "cold-start resume view", detail: { kind: "section", spec: "3",
      title: "HANDOFF.md",
      body: "The view that lets somebody else — or a later session with no context — "
        + "pick the work up. Graduates out of notebook.md when it earns its own file." } },
    { path: "lessons.md", note: "end-of-life distillation", detail: { kind: "section", spec: "3",
      title: "lessons.md",
      body: "What this notebook learned that the next one should not have to. The "
        + "unit of compounding across a beat." } }
  ];

  var buttons = [];

  function showDetail(entry) {
    var host = document.getElementById("detail");
    host.textContent = "";
    var detail = entry.detail;

    var head = document.createElement("div");
    head.className = "spec-detail__head";
    var title = document.createElement("h3");
    var link = document.createElement("a");
    link.className = "spec-link";

    if (detail.kind === "entity") {
      var record = entity(detail.type);
      if (!record) return;
      title.textContent = record.dir;
      link.href = kit.specHref(record.spec, spec.sections);
      link.textContent = kit.specLabel(record.spec, spec.sections) + " →";
      head.appendChild(title);
      head.appendChild(link);
      host.appendChild(head);

      var typeLine = document.createElement("p");
      typeLine.innerHTML = "<code>type: " + kit.esc(record.type) + "</code> · ids "
        + "<code>" + kit.esc(record.id_prefix) + "</code>";
      host.appendChild(typeLine);

      var summary = document.createElement("p");
      summary.textContent = record.summary;
      host.appendChild(summary);

      var keysLabel = document.createElement("p");
      keysLabel.className = "pane-label";
      keysLabel.textContent = "Frontmatter keys written by flip "
        + (meta ? meta.version : "");
      host.appendChild(keysLabel);

      var keys = document.createElement("ul");
      keys.className = "keylist";
      record.observed_keys.forEach(function (key) {
        var item = document.createElement("li");
        item.textContent = key;
        if (OKF_CORE.indexOf(key) === -1) {
          item.className = "is-extension";
          item.title = "flip extension vocabulary — OKF consumers preserve and may ignore it";
        } else {
          item.title = "OKF core key";
        }
        keys.appendChild(item);
      });
      host.appendChild(keys);

      var legend = document.createElement("p");
      legend.className = "record__caption";
      legend.style.padding = "0";
      legend.style.border = "0";
      legend.textContent = "Accented keys are flip's extension vocabulary; the rest "
        + "are OKF core. These are the keys the implementation wrote when this page "
        + "was built, not a list from the prose.";
      host.appendChild(legend);
      return;
    }

    title.textContent = detail.title;
    link.href = kit.specHref(detail.spec, spec.sections);
    link.textContent = kit.specLabel(detail.spec, spec.sections) + " →";
    head.appendChild(title);
    head.appendChild(link);
    host.appendChild(head);
    var body = document.createElement("p");
    body.textContent = detail.body;
    host.appendChild(body);
  }

  function renderLayout() {
    var host = document.getElementById("bundle");
    var root = document.createElement("ul");

    function line(entry, list) {
      var item = document.createElement("li");
      var label = (entry.dir || entry.path);
      if (entry.detail) {
        var button = document.createElement("button");
        button.type = "button";
        button.innerHTML = kit.esc(label)
          + ' <span class="comment">' + kit.esc(entry.note || "") + "</span>";
        button.addEventListener("click", function () {
          buttons.forEach(function (b) { b.removeAttribute("aria-current"); });
          button.setAttribute("aria-current", "true");
          showDetail(entry);
        });
        buttons.push(button);
        item.appendChild(button);
      } else {
        var plain = document.createElement("span");
        plain.className = "plain";
        plain.innerHTML = kit.esc(label)
          + ' <span class="comment">' + kit.esc(entry.note || "") + "</span>";
        item.appendChild(plain);
      }
      if (entry.children) {
        var sub = document.createElement("ul");
        entry.children.forEach(function (child) { line(child, sub); });
        item.appendChild(sub);
      }
      list.appendChild(item);
    }

    LAYOUT.forEach(function (entry) { line(entry, root); });
    host.appendChild(root);

    if (buttons.length) {
      buttons[0].setAttribute("aria-current", "true");
      showDetail(LAYOUT[0]);
    }
  }

  function renderRail() {
    var host = document.getElementById("rail");
    spec.lifecycle.forEach(function (stage, i) {
      var cell = document.createElement("div");
      cell.className = "rail__stage";
      if (i === 1 || i === 4) cell.setAttribute("data-gate", "yes");

      var name = document.createElement("span");
      name.className = "rail__name";
      name.textContent = (i + 1) + ". " + stage.stage;
      cell.appendChild(name);

      var act = document.createElement("code");
      act.className = "rail__act";
      act.textContent = stage.act;
      cell.appendChild(act);

      var gains = document.createElement("p");
      gains.textContent = stage.gains;
      cell.appendChild(gains);

      var worth = document.createElement("p");
      worth.className = "rail__worth";
      worth.textContent = stage.worth;
      cell.appendChild(worth);

      host.appendChild(cell);
    });
  }

  function table(host, headers, rows) {
    var thead = document.createElement("thead");
    var hr = document.createElement("tr");
    headers.forEach(function (text) {
      var th = document.createElement("th");
      th.scope = "col";
      th.textContent = text;
      hr.appendChild(th);
    });
    thead.appendChild(hr);
    host.appendChild(thead);

    var tbody = document.createElement("tbody");
    rows.forEach(function (cells) {
      var tr = document.createElement("tr");
      cells.forEach(function (cell) {
        var td = document.createElement("td");
        if (cell && cell.nodeType) td.appendChild(cell);
        else td.textContent = cell;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    host.appendChild(tbody);
  }

  function code(text) {
    var node = document.createElement("code");
    node.textContent = text;
    return node;
  }

  function renderLedgers() {
    table(
      document.getElementById("ledgers"),
      ["Ledger", "Path", "What one line records"],
      spec.ledgers.map(function (row) {
        var link = document.createElement("a");
        link.href = kit.specHref(row.spec, spec.sections);
        link.textContent = row.label;
        return [link, code(row.path), row.summary];
      })
    );
  }

  function renderProfiles() {
    table(
      document.getElementById("profiles"),
      ["Profile", "Intent", "Requires beyond the core"],
      spec.profiles.map(function (row) {
        return [code(row.id), row.intent, row.requires];
      })
    );
  }

  function renderCli() {
    if (!meta || !meta.cli) return;
    var host = document.getElementById("cli");
    var groups = {};
    meta.cli.commands.forEach(function (command) {
      var key = command.group || "flip";
      groups[key] = groups[key] || [];
      groups[key].push(command);
    });

    Object.keys(groups).sort(function (a, b) {
      if (a === "flip") return -1;
      if (b === "flip") return 1;
      return a.localeCompare(b);
    }).forEach(function (key, i) {
      var details = document.createElement("details");
      details.className = "cli-group";
      if (i === 0) details.open = true;
      var summary = document.createElement("summary");
      summary.textContent = key + " — " + groups[key].length + " command"
        + (groups[key].length === 1 ? "" : "s");
      details.appendChild(summary);

      var wrap = document.createElement("div");
      wrap.className = "table-wrap";
      var tableEl = document.createElement("table");
      tableEl.className = "cli-table";
      table(tableEl, ["Command", "Purpose"], groups[key].map(function (command) {
        return [command.command, command.purpose || ""];
      }));
      wrap.appendChild(tableEl);
      details.appendChild(wrap);
      host.appendChild(details);
    });
  }

  function renderSections() {
    var host = document.getElementById("sections");
    var list = document.createElement("div");
    list.className = "card-grid";
    spec.sections.forEach(function (section) {
      var link = document.createElement("a");
      link.className = "card";
      link.href = SPEC_URL + "#" + section.anchor;
      var heading = document.createElement("h3");
      heading.style.marginTop = "0";
      heading.style.fontSize = "var(--text-base)";
      heading.textContent = "§" + section.number + " " + section.title.replace(/`/g, "");
      link.appendChild(heading);
      list.appendChild(link);
    });
    host.appendChild(list);
  }

  renderLayout();
  renderRail();
  renderLedgers();
  renderProfiles();
  renderCli();
  renderSections();
})();
