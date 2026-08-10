/* The notebook viewer: the canonical render of a whole flip notebook.

   Data-driven from site/data/demo-notebook.js (window.__FLIP_NOTEBOOK__), the
   flip-render/2 projection of the scratch notebook this site's build creates
   by running the real CLI (see website/build.py). Nothing here invents a
   fact — a field the projection omits (freshness, sha256, forecasts, a
   question's watching surface) simply does not render. Every entity gets a
   stable anchor id (#F1, #C1, #Q1, #D1 …) so a claim's cited sources link
   straight to the source's own row. */
(function () {
  "use strict";

  var nb = window.__FLIP_NOTEBOOK__;
  if (!nb) return; // the authored fallback (empty tables, noscript note) stays as written

  var GRADE_ORDER = { A: 0, B: 1, C: 2, "?": 3 };

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function td(content) {
    var cell = document.createElement("td");
    if (content instanceof Node) cell.appendChild(content);
    else if (content != null) cell.textContent = content;
    return cell;
  }

  function present(value) {
    if (value == null) return false;
    if (typeof value === "string") return value.trim() !== "";
    if (Array.isArray(value)) return value.length > 0;
    return true;
  }

  // -- badges -----------------------------------------------------------------

  function gradeBadge(grade) {
    var g = grade || "?";
    var b = el("span", "badge provenance__grade", g);
    b.setAttribute("data-grade", g);
    b.title = g === "?" ? "ungraded — captured, not yet judged" : "grade " + g;
    return b;
  }

  function statusBadge(status) {
    var s = status || "asserted";
    var cls = "badge";
    if (s === "verified") cls += " badge--success";
    else if (s === "needs-2nd" || s === "asserted") cls += " badge--warn";
    return el("span", cls, s);
  }

  function questionStatusBadge(status) {
    var s = status || "open";
    var cls = "badge" + (s === "open" ? " badge--accent" : "");
    return el("span", cls, s);
  }

  // -- formatting helpers ------------------------------------------------------

  function supportSummary(support) {
    if (!support) return "";
    var bits = [];
    if (present(support.basis)) bits.push(String(support.basis));
    if (present(support.n)) bits.push("n=" + support.n);
    if (present(support.method)) bits.push(String(support.method));
    if (present(support.vintage)) bits.push("vintage " + support.vintage);
    if (support.base_defined === true) bits.push("base defined");
    else if (support.base_defined === false) bits.push("base not defined");
    return bits.join(" · ");
  }

  function shortSha(sha) {
    if (!present(sha)) return "";
    return String(sha).slice(0, 12) + "…";
  }

  function stamp(iso) {
    if (!present(iso)) return "";
    return String(iso).replace("T", " ").replace(/(\.\d+)?Z$/, " UTC").replace("+00:00", " UTC");
  }

  function anchor(id, kind) {
    var a = el("a", "nb__ref", id);
    a.href = "#" + id;
    if (kind) a.title = kind + " " + id;
    return a;
  }

  // -- manifest -----------------------------------------------------------------

  function renderManifest() {
    var host = document.getElementById("nb-manifest");
    if (!host) return;
    var n = nb.notebook || {};
    var rows = [
      ["Slug", n.slug],
      ["Kind", n.kind],
      ["Status", n.status],
      ["Updated", n.updated],
      ["Notebook id", n.uid]
    ];
    rows.forEach(function (row) {
      if (!present(row[1])) return;
      var cell = el("div", "fact");
      cell.appendChild(el("dt", null, row[0]));
      cell.appendChild(el("dd", null, row[1]));
      host.appendChild(cell);
    });
  }

  // -- table of contents ---------------------------------------------------------

  function renderToc() {
    var host = document.getElementById("nb-toc");
    if (!host) return;
    var links = [
      ["sec-work", "Work", nb.work],
      ["sec-sources", "Sources", nb.sources],
      ["sec-claims", "Claims", nb.claims],
      ["sec-questions", "Questions", nb.questions],
      ["sec-decisions", "Decisions", nb.decisions],
      ["sec-sessions", "Sessions", nb.sessions],
      ["sec-forecasts", "Forecasts", nb.forecasts],
      ["sec-log", "Log", null]
    ];
    links.forEach(function (link) {
      // Optional lanes only earn a link when the projection carries them.
      if ((link[1] === "Forecasts" || link[1] === "Work") && !present(link[2])) return;
      var a = el("a", "nb__toc-link", link[1]);
      a.href = "#" + link[0];
      if (link[2]) {
        var count = Array.isArray(link[2]) ? link[2].length : null;
        if (count != null) a.appendChild(el("span", "nb__toc-count", String(count)));
      }
      host.appendChild(a);
    });
  }

  // -- the work ------------------------------------------------------------------
  // The prose the notebook exists to carry (working memory, findings), from the
  // projection's `work` array: [{path, title, body}], body in markdown. Rendered
  // by a deliberately small renderer — headings, paragraphs, blockquotes, lists,
  // tables, fenced code, bold/italic, links, inline code — with [C1]-style refs
  // linked to the matching entity anchors when the id exists in the projection.

  var workIds = null;
  function knownWorkIds() {
    if (workIds) return workIds;
    workIds = {};
    ["sources", "claims", "questions", "decisions", "sessions", "forecasts"]
      .forEach(function (lane) {
        (nb[lane] || []).forEach(function (item) {
          if (item && present(item.id)) workIds[item.id] = true;
        });
      });
    return workIds;
  }

  // First alternative that matches wins; link syntax outranks bare [C1] refs.
  var MD_INLINE = new RegExp(
    "(`[^`\\n]+`)" +                              // 1 inline code
    "|(\\*\\*[^*\\n]+\\*\\*)" +                   // 2 bold
    "|(\\*[^*\\n]+\\*)" +                         // 3 italic
    "|\\[([^\\]\\n]+)\\]\\(([^)\\s]+)\\)" +       // 4,5 link text, href
    "|\\[([A-Z]{1,3}\\d+)\\]"                     // 6 entity ref
  );

  function mdInline(text) {
    var frag = document.createDocumentFragment();
    var rest = String(text == null ? "" : text);
    var m;
    while ((m = MD_INLINE.exec(rest))) {
      if (m.index > 0) frag.appendChild(document.createTextNode(rest.slice(0, m.index)));
      if (m[1]) {
        frag.appendChild(el("code", null, m[1].slice(1, -1)));
      } else if (m[2]) {
        var strong = document.createElement("strong");
        strong.appendChild(mdInline(m[2].slice(2, -2)));
        frag.appendChild(strong);
      } else if (m[3]) {
        var emph = document.createElement("em");
        emph.appendChild(mdInline(m[3].slice(1, -1)));
        frag.appendChild(emph);
      } else if (m[4] != null) {
        var link = document.createElement("a");
        link.href = m[5];
        link.appendChild(mdInline(m[4]));
        frag.appendChild(link);
      } else if (m[6]) {
        if (knownWorkIds()[m[6]]) {
          var ref = anchor(m[6]);
          ref.textContent = m[0]; // keep the brackets the prose was written with
          frag.appendChild(ref);
        } else {
          frag.appendChild(document.createTextNode(m[0]));
        }
      }
      rest = rest.slice(m.index + m[0].length);
    }
    if (rest) frag.appendChild(document.createTextNode(rest));
    return frag;
  }

  var MD_TABLE_RULE = /^\s*\|?[\s:|-]*-[\s:|-]*\|?\s*$/;

  function mdTableCells(line) {
    return line.replace(/^\s*\|/, "").replace(/\|\s*$/, "").split("|")
      .map(function (cell) { return cell.trim(); });
  }

  function mdBlocks(text) {
    var host = el("div", "nb__md");
    var lines = String(text == null ? "" : text).replace(/\r\n?/g, "\n").split("\n");
    var i = 0;

    function listAt(marker) {
      var list = document.createElement(marker === "ol" ? "ol" : "ul");
      var re = marker === "ol" ? /^\s*\d+[.)]\s+(.*)$/ : /^\s*[-*+]\s+(.*)$/;
      var m2;
      while (i < lines.length && (m2 = lines[i].match(re))) {
        var item = document.createElement("li");
        item.appendChild(mdInline(m2[1]));
        list.appendChild(item);
        i += 1;
      }
      return list;
    }

    while (i < lines.length) {
      var line = lines[i];
      if (!line.trim()) { i += 1; continue; }
      var m = line.match(/^(#{1,6})\s+(.*)$/);
      if (m) {
        var heading = document.createElement("h" + m[1].length);
        heading.appendChild(mdInline(m[2]));
        host.appendChild(heading);
        i += 1;
        continue;
      }
      if (/^\s*(?:---+|\*\*\*+)\s*$/.test(line)) {
        host.appendChild(document.createElement("hr"));
        i += 1;
        continue;
      }
      if (/^```/.test(line)) {
        var fence = [];
        i += 1;
        while (i < lines.length && !/^```/.test(lines[i])) { fence.push(lines[i]); i += 1; }
        i += 1; // the closing fence
        var pre = document.createElement("pre");
        pre.appendChild(el("code", null, fence.join("\n")));
        host.appendChild(pre);
        continue;
      }
      if (/^\s*>/.test(line)) {
        var quoted = [];
        while (i < lines.length && /^\s*>/.test(lines[i])) {
          quoted.push(lines[i].replace(/^\s*>\s?/, ""));
          i += 1;
        }
        var quote = document.createElement("blockquote");
        var inner = mdBlocks(quoted.join("\n"));
        while (inner.firstChild) quote.appendChild(inner.firstChild);
        host.appendChild(quote);
        continue;
      }
      if (/^\s*[-*+]\s+/.test(line)) { host.appendChild(listAt("ul")); continue; }
      if (/^\s*\d+[.)]\s+/.test(line)) { host.appendChild(listAt("ol")); continue; }
      if (line.indexOf("|") !== -1 && i + 1 < lines.length && MD_TABLE_RULE.test(lines[i + 1])) {
        var table = document.createElement("table");
        var thead = document.createElement("thead");
        var headRow = document.createElement("tr");
        mdTableCells(line).forEach(function (cell) {
          var th = document.createElement("th");
          th.setAttribute("scope", "col");
          th.appendChild(mdInline(cell));
          headRow.appendChild(th);
        });
        thead.appendChild(headRow);
        table.appendChild(thead);
        var tbody = document.createElement("tbody");
        i += 2; // header + rule
        while (i < lines.length && lines[i].indexOf("|") !== -1 && lines[i].trim()) {
          var bodyRow = document.createElement("tr");
          mdTableCells(lines[i]).forEach(function (cell) {
            bodyRow.appendChild(td(mdInline(cell)));
          });
          tbody.appendChild(bodyRow);
          i += 1;
        }
        table.appendChild(tbody);
        var wrap = el("div", "table-wrap");
        wrap.appendChild(table);
        host.appendChild(wrap);
        continue;
      }
      var para = [];
      while (i < lines.length && lines[i].trim()
        && !/^(#{1,6}\s|\s*>|\s*[-*+]\s+|\s*\d+[.)]\s+|```)/.test(lines[i])) {
        para.push(lines[i].trim());
        i += 1;
      }
      var p = document.createElement("p");
      p.appendChild(mdInline(para.join(" ")));
      host.appendChild(p);
    }
    return host;
  }

  function renderWork() {
    if (!present(nb.work)) return; // no work lane, no section
    var section = document.getElementById("sec-work");
    var host = document.getElementById("nb-work");
    if (!section || !host) return;
    section.hidden = false;
    nb.work.forEach(function (doc) {
      var card = el("article", "nb__work-doc");
      var head = el("div", "nb__work-head");
      var title = doc.title || (doc.path === "notebook.md" ? "Working memory" : doc.path);
      head.appendChild(el("h3", null, title));
      if (present(doc.path)) head.appendChild(el("span", "nb__work-path", doc.path));
      card.appendChild(head);
      card.appendChild(mdBlocks(doc.body));
      host.appendChild(card);
    });
  }

  // -- sources --------------------------------------------------------------------

  function renderSources() {
    var host = document.getElementById("nb-sources");
    if (!host) return;
    var sources = (nb.sources || []).slice().sort(function (a, b) {
      return (GRADE_ORDER[a.grade] - GRADE_ORDER[b.grade]) || a.id.localeCompare(b.id);
    });
    sources.forEach(function (s) {
      var row = document.createElement("tr");
      row.id = s.id;

      row.appendChild(td(el("span", "nb__id", s.id)));
      row.appendChild(td(s.title || s.slug || s.id));
      row.appendChild(td(gradeBadge(s.grade)));
      row.appendChild(td(s.independence || ""));
      row.appendChild(td(supportSummary(s.support)));
      row.appendChild(td(s.freshness || ""));

      var provBits = [];
      if (present(s.provenance_state)) provBits.push(s.provenance_state);
      if (present(s.pipeline)) provBits.push("pipeline: " + s.pipeline);
      row.appendChild(td(provBits.join(" · ")));

      var custodyBits = [];
      if (present(s.sha256)) custodyBits.push("sha256 " + shortSha(s.sha256));
      if (present(s.captured_at)) custodyBits.push(stamp(s.captured_at));
      row.appendChild(td(custodyBits.join(" · ")));

      host.appendChild(row);
    });
  }

  // -- claims -----------------------------------------------------------------------

  function sourceRefs(ids) {
    var wrap = el("span", "nb__chips");
    (ids || []).forEach(function (id, i) {
      if (i > 0) wrap.appendChild(document.createTextNode(" "));
      wrap.appendChild(anchor(id, "source"));
    });
    return wrap;
  }

  function verificationChips(verifications) {
    var wrap = el("span", "nb__chips");
    (verifications || []).forEach(function (v) {
      var chip = el("span", "badge badge--accent", v.method || "verification");
      var meta = [];
      if (v.by) meta.push("by " + v.by);
      if (v.date) meta.push(v.date);
      if (meta.length) chip.title = meta.join(" · ");
      wrap.appendChild(chip);
    });
    if (!wrap.childNodes.length) wrap.appendChild(el("span", "nb__empty", "none"));
    return wrap;
  }

  function renderClaims() {
    var host = document.getElementById("nb-claims");
    if (!host) return;
    (nb.claims || []).forEach(function (c) {
      var row = document.createElement("tr");
      row.id = c.id;
      if (c.load_bearing) row.setAttribute("data-load-bearing", "true");

      row.appendChild(td(el("span", "nb__id", c.id)));
      row.appendChild(td(c.text || ""));
      row.appendChild(td(statusBadge(c.status)));
      row.appendChild(td(c.load_bearing ? el("span", "badge provenance__lb", "load-bearing") : ""));

      var value = "";
      if (present(c.value)) value = c.value + (present(c.unit) ? " " + c.unit : "");
      row.appendChild(td(value));

      row.appendChild(td(sourceRefs(c.sources)));
      // An absent corroboration count is not a zero: the claim cites only what it
      // is about, and that axis does not apply to it.
      var corr = "";
      if (c.corroboration != null) corr = String(c.corroboration);
      else if ((c.subjects || []).length || (c.sources || []).length) corr = "n/a (subject)";
      row.appendChild(td(corr));
      row.appendChild(td(present(c.exposure) ? el("span", "badge", c.exposure) : ""));
      row.appendChild(td(verificationChips(c.verifications)));

      host.appendChild(row);
    });
  }

  // -- questions --------------------------------------------------------------------

  function renderQuestions() {
    var host = document.getElementById("nb-questions");
    if (!host) return;
    (nb.questions || []).forEach(function (q) {
      var row = document.createElement("tr");
      row.id = q.id;

      row.appendChild(td(el("span", "nb__id", q.id)));
      row.appendChild(td(q.text || ""));
      row.appendChild(td(questionStatusBadge(q.status)));

      var watches = present(q.resolves_via) ? q.resolves_via.join(", ") : null;
      row.appendChild(td(watches ? watches : el("span", "badge badge--warn", "unwatched")));

      host.appendChild(row);
    });
  }

  // -- decisions --------------------------------------------------------------------

  function renderDecisions() {
    var host = document.getElementById("nb-decisions");
    if (!host) return;
    (nb.decisions || []).forEach(function (d) {
      var row = document.createElement("tr");
      row.id = d.id;

      row.appendChild(td(el("span", "nb__id", d.id)));

      var qd = el("div");
      if (present(d.question)) qd.appendChild(el("p", "nb__decision-q", d.question));
      qd.appendChild(el("p", "nb__decision-a", "→ " + (d.text || "")));
      row.appendChild(td(qd));

      var rejected = d.alternatives_rejected || [];
      if (rejected.length) {
        var list = el("ul", "nb__rejected");
        rejected.forEach(function (r) { list.appendChild(el("li", null, r)); });
        row.appendChild(td(list));
      } else {
        row.appendChild(td(el("span", "nb__empty", "none recorded")));
      }

      host.appendChild(row);
    });
  }

  // -- sessions ---------------------------------------------------------------------

  function renderSessions() {
    var host = document.getElementById("nb-sessions");
    if (!host) return;
    (nb.sessions || []).forEach(function (s) {
      var row = document.createElement("tr");
      if (present(s.id)) row.id = s.id;

      row.appendChild(td(s.actor || ""));
      row.appendChild(td(s.model || ""));
      row.appendChild(td(stamp(s.started)));
      row.appendChild(td(present(s.goal) ? s.goal : el("span", "nb__empty", "not recorded")));

      host.appendChild(row);
    });
  }

  // -- forecasts (tolerant of absence — another lane may add this array) -----------

  function renderForecasts() {
    if (!present(nb.forecasts)) return;
    var section = document.getElementById("sec-forecasts");
    var host = document.getElementById("nb-forecasts");
    if (!section || !host) return;
    section.hidden = false;
    nb.forecasts.forEach(function (f) {
      var row = document.createElement("tr");
      if (present(f.id)) row.id = f.id;

      row.appendChild(td(f.question || f.text || ""));

      var prob = "";
      if (present(f.probability)) prob = String(f.probability);
      else if (present(f.confidence)) prob = String(f.confidence);
      if (present(f.confidence) && present(f.probability)) prob += " (" + f.confidence + ")";
      row.appendChild(td(prob));

      row.appendChild(td(f.resolves_by || ""));
      row.appendChild(td(f.status || ""));

      host.appendChild(row);
    });
  }

  // -- log tail -----------------------------------------------------------------------

  function renderLog() {
    var host = document.getElementById("nb-log");
    if (!host) return;
    var entries = nb.log_tail || [];
    if (!entries.length) {
      var empty = el("li", "nb__empty", "No lines in this notebook's work log yet — none of the "
        + "build steps that created it appended to log/log.jsonl directly.");
      host.appendChild(empty);
      return;
    }
    entries.slice().reverse().forEach(function (line) {
      var item = document.createElement("li");
      item.className = "nb__log-line";
      item.appendChild(el("span", "nb__log-ts", stamp(line.ts)));
      item.appendChild(el("span", "nb__log-actor", line.actor || ""));
      item.appendChild(el("span", "nb__log-text", line.text || ""));
      host.appendChild(item);
    });
  }

  // -- vintage line in the footer --------------------------------------------------

  function renderVintage() {
    var host = document.getElementById("nb-vintage");
    if (!host || !nb.generated) return;
    var extra = document.createElement("span");
    extra.textContent = " Projection generated " + stamp(nb.generated) + " (" + nb.contract + ").";
    host.appendChild(extra);
  }

  renderManifest();
  renderToc();
  renderWork();
  renderSources();
  renderClaims();
  renderQuestions();
  renderDecisions();
  renderSessions();
  renderForecasts();
  renderLog();
  renderVintage();
})();
