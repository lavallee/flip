window.__FLIP_META__ = {
  "generated": "2026-08-20T21:41:21+00:00",
  "version": "0.21.0",
  "revision": "74ed222",
  "requires_python": ">=3.12",
  "dependencies": [
    "click>=8.1",
    "pyyaml>=6.0"
  ],
  "license": "MIT",
  "package": "flip-notebook",
  "tests": 1297,
  "spec_status": "draft v0.21 \u00b7 2026-08-18",
  "spec_lines": 2117,
  "skills": [
    "notebook-audit",
    "notebook-create",
    "notebook-handoff",
    "notebook-kind-author",
    "notebook-lessons",
    "notebook-log",
    "notebook-source"
  ],
  "cli": {
    "global_options": [
      "--version",
      "--notebook",
      "--actor"
    ],
    "commands": [
      {
        "command": "flip add-source",
        "group": "flip",
        "name": "add-source",
        "purpose": "Capture a source: fetch/copy into sources/raw/, hash it, open a page.",
        "arguments": [
          "TARGET"
        ],
        "options": [
          {
            "name": "--kind",
            "required": false
          },
          {
            "name": "--via",
            "required": false
          },
          {
            "name": "--note",
            "required": false
          },
          {
            "name": "--record",
            "required": false
          },
          {
            "name": "--extract",
            "required": false
          }
        ]
      },
      {
        "command": "flip ask",
        "group": "flip",
        "name": "ask",
        "purpose": "Ask [research].ask for cited synthesis \u2014 a grade-C lead, saved to sessions/raw/.",
        "arguments": [
          "QUERY"
        ],
        "options": [
          {
            "name": "--via",
            "required": false
          },
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip beat graduate",
        "group": "flip beat",
        "name": "graduate",
        "purpose": "Graduate a thread into a child notebook under notebooks/<slug>/.",
        "arguments": [
          "THREAD_ID",
          "NOTEBOOK_SLUG"
        ],
        "options": [
          {
            "name": "--kind",
            "required": false
          },
          {
            "name": "--title",
            "required": false
          }
        ]
      },
      {
        "command": "flip beat log",
        "group": "flip beat",
        "name": "log",
        "purpose": "Append one event to the beat work log (log/log.jsonl); actor auto-detected.",
        "arguments": [
          "TEXT"
        ],
        "options": []
      },
      {
        "command": "flip beat new",
        "group": "flip beat",
        "name": "new",
        "purpose": "Create a beat: index.md manifest + beat.md prompts, nothing else.",
        "arguments": [
          "SLUG"
        ],
        "options": [
          {
            "name": "--mission",
            "required": false
          },
          {
            "name": "--dest",
            "required": false
          }
        ]
      },
      {
        "command": "flip beat next",
        "group": "flip beat",
        "name": "next",
        "purpose": "What this beat should pick up next, ranked, with the reason for each.",
        "arguments": [],
        "options": [
          {
            "name": "--json",
            "required": false
          },
          {
            "name": "--limit",
            "required": false
          }
        ]
      },
      {
        "command": "flip beat show",
        "group": "flip beat",
        "name": "show",
        "purpose": "Show the beat triage view: ranked threads, dormant due, notebooks, log.",
        "arguments": [],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip beat thread add",
        "group": "flip beat thread",
        "name": "add",
        "purpose": "Open a thread, allocating the next TH#. Cite it in prose as [TH3].",
        "arguments": [
          "TITLE"
        ],
        "options": [
          {
            "name": "--kind",
            "required": true
          },
          {
            "name": "--note",
            "required": false
          },
          {
            "name": "--score",
            "required": false
          }
        ]
      },
      {
        "command": "flip beat thread drop",
        "group": "flip beat thread",
        "name": "drop",
        "purpose": "Drop a thread: negative coverage is first-class (SPEC \u00a714).",
        "arguments": [
          "THREAD_ID"
        ],
        "options": [
          {
            "name": "--reason",
            "required": true
          }
        ]
      },
      {
        "command": "flip beat thread update",
        "group": "flip beat thread",
        "name": "update",
        "purpose": "Update a thread in place: status, scores, next review, a dated note.",
        "arguments": [
          "THREAD_ID"
        ],
        "options": [
          {
            "name": "--status",
            "required": false
          },
          {
            "name": "--note",
            "required": false
          },
          {
            "name": "--score",
            "required": false
          },
          {
            "name": "--next-review",
            "required": false
          }
        ]
      },
      {
        "command": "flip claim add",
        "group": "flip claim",
        "name": "add",
        "purpose": "Assert a claim (status \"asserted\"), allocating the next C#.",
        "arguments": [
          "TEXT"
        ],
        "options": [
          {
            "name": "--source",
            "required": false
          },
          {
            "name": "--about",
            "required": false
          },
          {
            "name": "--load-bearing",
            "required": false
          },
          {
            "name": "--notes",
            "required": false
          },
          {
            "name": "--value",
            "required": false
          },
          {
            "name": "--unit",
            "required": false
          },
          {
            "name": "--absent-from",
            "required": false
          },
          {
            "name": "--surface",
            "required": false
          },
          {
            "name": "--derives-from",
            "required": false
          }
        ]
      },
      {
        "command": "flip claim derives add",
        "group": "flip claim derives",
        "name": "add",
        "purpose": "Declare CLAIM_ID rests on one or more other claims.",
        "arguments": [
          "CLAIM_ID",
          "ANCESTOR_ID..."
        ],
        "options": []
      },
      {
        "command": "flip claim derives rm",
        "group": "flip claim derives",
        "name": "rm",
        "purpose": "Drop a derivation edge from CLAIM_ID.",
        "arguments": [
          "CLAIM_ID",
          "ANCESTOR_ID"
        ],
        "options": []
      },
      {
        "command": "flip claim exposure",
        "group": "flip claim",
        "name": "exposure",
        "purpose": "Explain what a claim's test record adds up to, and why. Read-only.",
        "arguments": [
          "CLAIM_ID"
        ],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip claim list",
        "group": "flip claim",
        "name": "list",
        "purpose": "List claims, optionally filtered by status, stance or exposure.",
        "arguments": [],
        "options": [
          {
            "name": "--status",
            "required": false
          },
          {
            "name": "--stance",
            "required": false
          },
          {
            "name": "--exposure",
            "required": false
          },
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip claim rival",
        "group": "flip claim",
        "name": "rival",
        "purpose": "Declare two claims rivals \u2014 they answer the same question.",
        "arguments": [
          "CLAIM_ID",
          "RIVAL_ID"
        ],
        "options": [
          {
            "name": "--because",
            "required": true
          }
        ]
      },
      {
        "command": "flip claim source add",
        "group": "flip claim source",
        "name": "add",
        "purpose": "Link one or more sources to a claim. Unknown ids are refused.",
        "arguments": [
          "CLAIM_ID",
          "SOURCE_ID..."
        ],
        "options": [
          {
            "name": "--about",
            "required": false
          }
        ]
      },
      {
        "command": "flip claim source rm",
        "group": "flip claim source",
        "name": "rm",
        "purpose": "Unlink a source id from a claim. Refuses if the claim doesn't cite it.",
        "arguments": [
          "CLAIM_ID",
          "SOURCE_ID"
        ],
        "options": []
      },
      {
        "command": "flip claim stance",
        "group": "flip claim",
        "name": "stance",
        "purpose": "Record what is DONE with a claim, as opposed to what is known about it.",
        "arguments": [
          "CLAIM_ID",
          "STANCE"
        ],
        "options": [
          {
            "name": "--because",
            "required": true
          },
          {
            "name": "--falsifier",
            "required": false
          },
          {
            "name": "--holder",
            "required": false
          },
          {
            "name": "--source",
            "required": false
          }
        ]
      },
      {
        "command": "flip claim status",
        "group": "flip claim",
        "name": "status",
        "purpose": "Move a claim to a new status, recomputing its corroboration count.",
        "arguments": [
          "CLAIM_ID",
          "STATUS"
        ],
        "options": []
      },
      {
        "command": "flip claim supersede",
        "group": "flip claim",
        "name": "supersede",
        "purpose": "Concede a claim to the one that replaced it.",
        "arguments": [
          "CLAIM_ID"
        ],
        "options": [
          {
            "name": "--by",
            "required": true
          },
          {
            "name": "--because",
            "required": true
          }
        ]
      },
      {
        "command": "flip claim test",
        "group": "flip claim",
        "name": "test",
        "purpose": "Record a test run against a claim \u2014 including one that found the error.",
        "arguments": [
          "CLAIM_ID"
        ],
        "options": [
          {
            "name": "--probe",
            "required": true
          },
          {
            "name": "--error",
            "required": true
          },
          {
            "name": "--result",
            "required": true
          },
          {
            "name": "--would-detect",
            "required": false
          },
          {
            "name": "--if-absent",
            "required": false
          },
          {
            "name": "--against",
            "required": false
          },
          {
            "name": "--note",
            "required": false
          }
        ]
      },
      {
        "command": "flip claim verify",
        "group": "flip claim",
        "name": "verify",
        "purpose": "Record a verification on a claim (append-only frontmatter record).",
        "arguments": [
          "CLAIM_ID"
        ],
        "options": [
          {
            "name": "--method",
            "required": true
          },
          {
            "name": "--against",
            "required": false
          },
          {
            "name": "--note",
            "required": false
          }
        ]
      },
      {
        "command": "flip cli",
        "group": "flip",
        "name": "cli",
        "purpose": "Print a compact map of every command: group path, one-line purpose, key",
        "arguments": [],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip commission add",
        "group": "flip commission",
        "name": "add",
        "purpose": "Write a commission contract (status \"proposed\"), allocating the next K#.",
        "arguments": [
          "DELIVERABLE"
        ],
        "options": [
          {
            "name": "--universe",
            "required": true
          },
          {
            "name": "--stop",
            "required": true
          },
          {
            "name": "--does-not-redo",
            "required": true
          },
          {
            "name": "--for",
            "required": false
          },
          {
            "name": "--roi-low",
            "required": false
          },
          {
            "name": "--roi-high",
            "required": false
          }
        ]
      },
      {
        "command": "flip commission list",
        "group": "flip commission",
        "name": "list",
        "purpose": "List commission contracts: id \u00b7 status \u00b7 deliverable \u00b7 for.",
        "arguments": [],
        "options": [
          {
            "name": "--status",
            "required": false
          },
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip commission status",
        "group": "flip commission",
        "name": "status",
        "purpose": "Move a commission along proposed \u2192 dispatched \u2192 returned | declined.",
        "arguments": [
          "ID",
          "STATUS"
        ],
        "options": [
          {
            "name": "--note",
            "required": false
          },
          {
            "name": "--consumed",
            "required": false
          }
        ]
      },
      {
        "command": "flip config init",
        "group": "flip config",
        "name": "init",
        "purpose": "Write a starter config.toml: a bundled web fetcher plus commented examples.",
        "arguments": [],
        "options": [
          {
            "name": "--force",
            "required": false
          }
        ]
      },
      {
        "command": "flip config show",
        "group": "flip config",
        "name": "show",
        "purpose": "List the integration lanes configured on this machine \u2014 what flip can run.",
        "arguments": [],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip decide",
        "group": "flip",
        "name": "decide",
        "purpose": "Record a decision page (decisions/<slug>.md), allocating the next D#.",
        "arguments": [],
        "options": [
          {
            "name": "--question",
            "required": true
          },
          {
            "name": "--decision",
            "required": true
          },
          {
            "name": "--why",
            "required": true
          },
          {
            "name": "--rejected",
            "required": false
          }
        ]
      },
      {
        "command": "flip discipline list",
        "group": "flip discipline",
        "name": "list",
        "purpose": "List every visible discipline: built-in, user, and notebook-local.",
        "arguments": [],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip discipline new",
        "group": "flip discipline",
        "name": "new",
        "purpose": "Scaffold $FLIP_HOME/disciplines/<id>.toml from a commented template.",
        "arguments": [
          "ID"
        ],
        "options": [
          {
            "name": "--force",
            "required": false
          }
        ]
      },
      {
        "command": "flip discipline show",
        "group": "flip discipline",
        "name": "show",
        "purpose": "Show a discipline's slots, gates, and checks \u2014 the composable shape.",
        "arguments": [
          "ID"
        ],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip doctor",
        "group": "flip",
        "name": "doctor",
        "purpose": "Lint the notebook against the spec and its profile; exit 1 on errors.",
        "arguments": [],
        "options": [
          {
            "name": "--json",
            "required": false
          },
          {
            "name": "--workspace",
            "required": false
          },
          {
            "name": "--fix",
            "required": false
          },
          {
            "name": "--code",
            "required": false
          },
          {
            "name": "--limit",
            "required": false
          }
        ]
      },
      {
        "command": "flip export bag",
        "group": "flip export",
        "name": "bag",
        "purpose": "Write a BagIt 1.0 bag of the notebook at DEST for cold archival.",
        "arguments": [
          "DEST"
        ],
        "options": []
      },
      {
        "command": "flip export csl",
        "group": "flip export",
        "name": "csl",
        "purpose": "Emit CSL JSON from the references/ pages for citation managers (Zotero etc.).",
        "arguments": [],
        "options": [
          {
            "name": "--output",
            "required": false
          }
        ]
      },
      {
        "command": "flip export json",
        "group": "flip export",
        "name": "json",
        "purpose": "Emit the flip-render/1 (or /2) JSON projection for renderers and site generators.",
        "arguments": [],
        "options": [
          {
            "name": "--out",
            "required": false
          },
          {
            "name": "--include-private",
            "required": false
          },
          {
            "name": "--render-version",
            "required": false
          }
        ]
      },
      {
        "command": "flip export okf",
        "group": "flip export",
        "name": "okf",
        "purpose": "Copy the notebook to DEST as an outside-facing OKF bundle (policy filter).",
        "arguments": [
          "DEST"
        ],
        "options": [
          {
            "name": "--include-private",
            "required": false
          },
          {
            "name": "--announce",
            "required": false
          }
        ]
      },
      {
        "command": "flip extract",
        "group": "flip",
        "name": "extract",
        "purpose": "Derive sources/text/<ID>.txt from a captured source's raw bytes.",
        "arguments": [
          "SOURCE_ID"
        ],
        "options": [
          {
            "name": "--via",
            "required": false
          },
          {
            "name": "--force",
            "required": false
          },
          {
            "name": "--note",
            "required": false
          },
          {
            "name": "--method",
            "required": false
          }
        ]
      },
      {
        "command": "flip find",
        "group": "flip",
        "name": "find",
        "purpose": "Find candidate sources for a question via [research].find \u2014 leads, not captures.",
        "arguments": [
          "QUERY"
        ],
        "options": [
          {
            "name": "--via",
            "required": false
          },
          {
            "name": "--capture",
            "required": false
          },
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip forecast add",
        "group": "flip forecast",
        "name": "add",
        "purpose": "Open a forecast (status \"open\"), allocating the next FC#.",
        "arguments": [
          "QUESTION"
        ],
        "options": [
          {
            "name": "--resolves-by",
            "required": false
          },
          {
            "name": "--resolves-via",
            "required": false
          },
          {
            "name": "--annul-if",
            "required": false
          },
          {
            "name": "--probability",
            "required": false
          },
          {
            "name": "--confidence",
            "required": false
          },
          {
            "name": "--criteria",
            "required": false
          },
          {
            "name": "--ladder",
            "required": false
          },
          {
            "name": "--resolver",
            "required": false
          },
          {
            "name": "--base-rate",
            "required": false
          },
          {
            "name": "--predictability",
            "required": false
          },
          {
            "name": "--bears-on",
            "required": false
          },
          {
            "name": "--generated-by",
            "required": false
          },
          {
            "name": "--horizon",
            "required": false
          }
        ]
      },
      {
        "command": "flip forecast decline",
        "group": "flip forecast",
        "name": "decline",
        "purpose": "Record a declined generated question in log/declined-forecasts.jsonl.",
        "arguments": [
          "TEXT"
        ],
        "options": [
          {
            "name": "--reason",
            "required": true
          },
          {
            "name": "--fold-into",
            "required": false
          }
        ]
      },
      {
        "command": "flip forecast due",
        "group": "flip forecast",
        "name": "due",
        "purpose": "List open forecasts past or near their resolves_by date, soonest first.",
        "arguments": [],
        "options": [
          {
            "name": "--within",
            "required": false
          },
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip forecast list",
        "group": "flip forecast",
        "name": "list",
        "purpose": "List every forecast (and cluster): id \u00b7 status \u00b7 resolves_by \u00b7 p/c \u00b7 question.",
        "arguments": [],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip forecast resolve",
        "group": "flip forecast",
        "name": "resolve",
        "purpose": "Resolve a forecast on its surface: yes | no | void. Final.",
        "arguments": [
          "FORECAST_ID",
          "OUTCOME"
        ],
        "options": [
          {
            "name": "--note",
            "required": false
          }
        ]
      },
      {
        "command": "flip forecast update",
        "group": "flip forecast",
        "name": "update",
        "purpose": "Move a forecast's current estimate; the old one stays in `updates:`.",
        "arguments": [
          "FORECAST_ID"
        ],
        "options": [
          {
            "name": "--probability",
            "required": false
          },
          {
            "name": "--confidence",
            "required": false
          },
          {
            "name": "--note",
            "required": false
          }
        ]
      },
      {
        "command": "flip grade",
        "group": "flip",
        "name": "grade",
        "purpose": "Record the support tuple on a source's page (SPEC \u00a75.4).",
        "arguments": [
          "SOURCE_ID"
        ],
        "options": [
          {
            "name": "--independence",
            "required": false
          },
          {
            "name": "--basis",
            "required": false
          },
          {
            "name": "--n",
            "required": false
          },
          {
            "name": "--method",
            "required": false
          },
          {
            "name": "--vintage",
            "required": false
          },
          {
            "name": "--base-defined",
            "required": false
          },
          {
            "name": "--freshness",
            "required": false
          },
          {
            "name": "--notes",
            "required": false
          },
          {
            "name": "--explain",
            "required": false
          },
          {
            "name": "--grade",
            "required": false
          }
        ]
      },
      {
        "command": "flip import",
        "group": "flip",
        "name": "import",
        "purpose": "Import a shared notebook (directory, OKF export, or BagIt bag).",
        "arguments": [
          "SRC"
        ],
        "options": [
          {
            "name": "--as",
            "required": false
          },
          {
            "name": "--into",
            "required": false
          },
          {
            "name": "--update",
            "required": false
          }
        ]
      },
      {
        "command": "flip index",
        "group": "flip",
        "name": "index",
        "purpose": "Rebuild the per-user registry: scan roots, rewrite $FLIP_HOME/index.jsonl.",
        "arguments": [],
        "options": [
          {
            "name": "--root",
            "required": false
          }
        ]
      },
      {
        "command": "flip kind adopt",
        "group": "flip kind",
        "name": "adopt",
        "purpose": "Adopt a kind onto this notebook: set manifest kind, log a",
        "arguments": [
          "ID"
        ],
        "options": []
      },
      {
        "command": "flip kind list",
        "group": "flip kind",
        "name": "list",
        "purpose": "List every visible kind: built-in, user, notebook-local, and profiles.",
        "arguments": [],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip kind new",
        "group": "flip kind",
        "name": "new",
        "purpose": "Scaffold $FLIP_HOME/kinds/<id>.toml from a commented template.",
        "arguments": [
          "ID"
        ],
        "options": [
          {
            "name": "--force",
            "required": false
          }
        ]
      },
      {
        "command": "flip kind show",
        "group": "flip kind",
        "name": "show",
        "purpose": "Show a kind's contract and workflow \u2014 the doctor-checkable shape.",
        "arguments": [
          "ID"
        ],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip log",
        "group": "flip",
        "name": "log",
        "purpose": "Append one event to the work log (log/log.jsonl); actor auto-detected.",
        "arguments": [
          "TEXT"
        ],
        "options": []
      },
      {
        "command": "flip migrate",
        "group": "flip",
        "name": "migrate",
        "purpose": "Upgrade a notebook in place to the current profile version.",
        "arguments": [],
        "options": []
      },
      {
        "command": "flip new",
        "group": "flip",
        "name": "new",
        "purpose": "Create a notebook: index.md manifest + notebook.md stubs, nothing else.",
        "arguments": [
          "SLUG"
        ],
        "options": [
          {
            "name": "--kind",
            "required": false
          },
          {
            "name": "--title",
            "required": false
          },
          {
            "name": "--visibility",
            "required": false
          },
          {
            "name": "--dest",
            "required": false
          }
        ]
      },
      {
        "command": "flip obsidian",
        "group": "flip",
        "name": "obsidian",
        "purpose": "Prepare the notebook (or beat) to open cleanly as an Obsidian vault.",
        "arguments": [],
        "options": [
          {
            "name": "--no-plugin",
            "required": false
          }
        ]
      },
      {
        "command": "flip open",
        "group": "flip",
        "name": "open",
        "purpose": "Resolve a reference (A3, C7 \u2026 or recipes:A3) to its entity page path.",
        "arguments": [
          "REF"
        ],
        "options": []
      },
      {
        "command": "flip pass",
        "group": "flip",
        "name": "pass",
        "purpose": "Record negative evidence \u2014 considered and rejected \u2014 in log/passed.jsonl.",
        "arguments": [
          "TEXT"
        ],
        "options": [
          {
            "name": "--reason",
            "required": true
          },
          {
            "name": "--url",
            "required": false
          },
          {
            "name": "--absent-from",
            "required": false
          },
          {
            "name": "--surface",
            "required": false
          }
        ]
      },
      {
        "command": "flip profiles",
        "group": "flip",
        "name": "profiles",
        "purpose": "List available notebook profiles (kinds) for `flip new --kind`.",
        "arguments": [],
        "options": []
      },
      {
        "command": "flip question add",
        "group": "flip question",
        "name": "add",
        "purpose": "Open a question, allocating the next Q#. Cite it in prose as [Q2].",
        "arguments": [
          "TEXT"
        ],
        "options": [
          {
            "name": "--resolves-via",
            "required": false
          }
        ]
      },
      {
        "command": "flip question answer",
        "group": "flip question",
        "name": "answer",
        "purpose": "Mark a question answered: status, answered timestamp, and actor land",
        "arguments": [
          "ID"
        ],
        "options": [
          {
            "name": "--note",
            "required": false
          },
          {
            "name": "--reopen-when",
            "required": false
          }
        ]
      },
      {
        "command": "flip question close",
        "group": "flip question",
        "name": "close",
        "purpose": "Close a question without an answer \u2014 split, yielded to its owner,",
        "arguments": [
          "ID"
        ],
        "options": [
          {
            "name": "--reason",
            "required": true
          },
          {
            "name": "--note",
            "required": false
          },
          {
            "name": "--reopen-when",
            "required": false
          }
        ]
      },
      {
        "command": "flip question dormant",
        "group": "flip question",
        "name": "dormant",
        "purpose": "Park an open question with a review date (dormant is not dead).",
        "arguments": [
          "ID"
        ],
        "options": [
          {
            "name": "--until",
            "required": true
          },
          {
            "name": "--note",
            "required": false
          }
        ]
      },
      {
        "command": "flip question list",
        "group": "flip question",
        "name": "list",
        "purpose": "List every question with its current status: id \u00b7 status \u00b7 text.",
        "arguments": [],
        "options": [
          {
            "name": "--status",
            "required": false
          },
          {
            "name": "--armed",
            "required": false
          },
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip question note",
        "group": "flip question",
        "name": "note",
        "purpose": "Land evidence on a question without closing it (append-only).",
        "arguments": [
          "ID",
          "TEXT"
        ],
        "options": [
          {
            "name": "--answers",
            "required": false
          },
          {
            "name": "--source",
            "required": false
          },
          {
            "name": "--zero-yield",
            "required": false
          }
        ]
      },
      {
        "command": "flip question reopen",
        "group": "flip question",
        "name": "reopen",
        "purpose": "Reopen a settled question (answered, closed, or dormant \u2192 open).",
        "arguments": [
          "ID"
        ],
        "options": [
          {
            "name": "--because",
            "required": true
          }
        ]
      },
      {
        "command": "flip question repose",
        "group": "flip question",
        "name": "repose",
        "purpose": "Re-pose a question with a sharper formulation (append-only).",
        "arguments": [
          "ID",
          "TEXT"
        ],
        "options": [
          {
            "name": "--sharpened",
            "required": false
          },
          {
            "name": "--note",
            "required": false
          }
        ]
      },
      {
        "command": "flip recall",
        "group": "flip",
        "name": "recall",
        "purpose": "Recall what we already hold locally via [knowledge].recall (read-only).",
        "arguments": [
          "QUERY"
        ],
        "options": [
          {
            "name": "--via",
            "required": false
          },
          {
            "name": "--record",
            "required": false
          },
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip rename",
        "group": "flip",
        "name": "rename",
        "purpose": "Rename an entity page to NEW_SLUG, rewriting links notebook-wide.",
        "arguments": [
          "ID",
          "NEW_SLUG"
        ],
        "options": []
      },
      {
        "command": "flip resolve",
        "group": "flip",
        "name": "resolve",
        "purpose": "Resolve a reference to its entity page, with provenance.",
        "arguments": [
          "REF"
        ],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip session end",
        "group": "flip session",
        "name": "end",
        "purpose": "Close a session: `ended` lands in its frontmatter, the summary in its body.",
        "arguments": [
          "SLUG_OR_PATH"
        ],
        "options": [
          {
            "name": "--summary",
            "required": true
          }
        ]
      },
      {
        "command": "flip session start",
        "group": "flip session",
        "name": "start",
        "purpose": "Open sessions/<UTC stamp>-<slug>.md with frontmatter and stubs.",
        "arguments": [
          "SLUG"
        ],
        "options": [
          {
            "name": "--model",
            "required": false
          },
          {
            "name": "--tools",
            "required": false
          }
        ]
      },
      {
        "command": "flip session transcript",
        "group": "flip session",
        "name": "transcript",
        "purpose": "Keep this session's conversation verbatim, as a citable source.",
        "arguments": [
          "SLUG_OR_PATH"
        ],
        "options": [
          {
            "name": "--file",
            "required": true
          },
          {
            "name": "--title",
            "required": false
          },
          {
            "name": "--participant",
            "required": false
          },
          {
            "name": "--model",
            "required": false
          },
          {
            "name": "--note",
            "required": false
          }
        ]
      },
      {
        "command": "flip show",
        "group": "flip",
        "name": "show",
        "purpose": "Show a computed view of the notebook; default is the hot view.",
        "arguments": [],
        "options": [
          {
            "name": "--claims",
            "required": false
          },
          {
            "name": "--stale",
            "required": false
          },
          {
            "name": "--forecasts",
            "required": false
          },
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip source list",
        "group": "flip source",
        "name": "list",
        "purpose": "List sources: id \u00b7 grade/independence/freshness \u00b7 title \u00b7 page path.",
        "arguments": [],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip source pipeline",
        "group": "flip source",
        "name": "pipeline",
        "purpose": "Classify a source's pipeline liveness \u2014 did the thing that produced it",
        "arguments": [
          "SOURCE_ID",
          "live|dormant|orphaned|transferred:<steward>"
        ],
        "options": [
          {
            "name": "--evidence",
            "required": true
          }
        ]
      },
      {
        "command": "flip source provenance",
        "group": "flip source",
        "name": "provenance",
        "purpose": "Record where the provenance chain-walk behind this source ended.",
        "arguments": [
          "SOURCE_ID",
          "STATE"
        ],
        "options": [
          {
            "name": "--note",
            "required": false
          }
        ]
      },
      {
        "command": "flip source recheck",
        "group": "flip source",
        "name": "recheck",
        "purpose": "Re-fetch a source's canonical URL and compare against custody.",
        "arguments": [
          "SOURCE_ID"
        ],
        "options": [
          {
            "name": "--via",
            "required": false
          }
        ]
      },
      {
        "command": "flip source retitle",
        "group": "flip source",
        "name": "retitle",
        "purpose": "Rewrite a source's title (and its `# heading`), quoting it correctly.",
        "arguments": [
          "SOURCE_ID",
          "TITLE"
        ],
        "options": []
      },
      {
        "command": "flip transcript excerpt",
        "group": "flip transcript",
        "name": "excerpt",
        "purpose": "Pin lines A-B of a transcript under LABEL, and print the ref to cite.",
        "arguments": [
          "ID"
        ],
        "options": [
          {
            "name": "--lines",
            "required": true
          },
          {
            "name": "--label",
            "required": true
          },
          {
            "name": "--note",
            "required": false
          }
        ]
      },
      {
        "command": "flip transcript list",
        "group": "flip transcript",
        "name": "list",
        "purpose": "Every passage pinned on a transcript, in the order they were pinned.",
        "arguments": [
          "ID"
        ],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip transcript unpin",
        "group": "flip transcript",
        "name": "unpin",
        "purpose": "Drop a pinned passage. Refuses while a claim still cites it.",
        "arguments": [
          "ID",
          "LABEL"
        ],
        "options": []
      },
      {
        "command": "flip ws add",
        "group": "flip ws",
        "name": "add",
        "purpose": "Bind a notebook already on disk to a handle in this workspace.",
        "arguments": [
          "PATH"
        ],
        "options": [
          {
            "name": "--as",
            "required": false
          }
        ]
      },
      {
        "command": "flip ws init",
        "group": "flip ws",
        "name": "init",
        "purpose": "Declare the current directory a workspace root and bind what's here.",
        "arguments": [],
        "options": []
      },
      {
        "command": "flip ws list",
        "group": "flip ws",
        "name": "list",
        "purpose": "List bound notebooks: handle \u00b7 slug \u00b7 uid \u00b7 path (status flags problems).",
        "arguments": [],
        "options": [
          {
            "name": "--json",
            "required": false
          }
        ]
      },
      {
        "command": "flip ws rename",
        "group": "flip ws",
        "name": "rename",
        "purpose": "Rebind a handle, rewriting qualified refs (old:A3 \u2192 new:A3) workspace-wide.",
        "arguments": [
          "OLD",
          "NEW"
        ],
        "options": []
      },
      {
        "command": "flip ws rm",
        "group": "flip ws",
        "name": "rm",
        "purpose": "Unbind a handle (files stay on disk; only the binding and its",
        "arguments": [
          "HANDLE"
        ],
        "options": []
      },
      {
        "command": "flip ws show",
        "group": "flip ws",
        "name": "show",
        "purpose": "Merged roster across bound notebooks: open questions (with re-pose",
        "arguments": [],
        "options": [
          {
            "name": "--open",
            "required": false
          },
          {
            "name": "--claims",
            "required": false
          },
          {
            "name": "--json",
            "required": false
          }
        ]
      }
    ]
  }
};
