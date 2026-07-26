window.__FLIP_SPEC__ = {
  "generated": "2026-07-26T00:59:00+00:00",
  "sections": [
    {
      "number": "1",
      "title": "Principles",
      "anchor": "1-principles"
    },
    {
      "number": "2",
      "title": "Definitions",
      "anchor": "2-definitions"
    },
    {
      "number": "3",
      "title": "Directory layout",
      "anchor": "3-directory-layout"
    },
    {
      "number": "4",
      "title": "The manifest \u2014 root `index.md` frontmatter",
      "anchor": "4-the-manifest--root-indexmd-frontmatter"
    },
    {
      "number": "5",
      "title": "Sources \u2014 custody, entity pages, provenance",
      "anchor": "5-sources--custody-entity-pages-provenance"
    },
    {
      "number": "6",
      "title": "The flip profile \u2014 lineage rules for LLM-built wikis",
      "anchor": "6-the-flip-profile--lineage-rules-for-llm-built-wikis"
    },
    {
      "number": "7",
      "title": "Claims and forecasts \u2014 the two-object rule",
      "anchor": "7-claims-and-forecasts--the-two-object-rule"
    },
    {
      "number": "8",
      "title": "Logs \u2014 events, sessions, views",
      "anchor": "8-logs--events-sessions-views"
    },
    {
      "number": "9",
      "title": "IDs, filenames, and links",
      "anchor": "9-ids-filenames-and-links"
    },
    {
      "number": "10",
      "title": "Views",
      "anchor": "10-views"
    },
    {
      "number": "11",
      "title": "Renders and drafts",
      "anchor": "11-renders-and-drafts"
    },
    {
      "number": "12",
      "title": "Working with humans (the Obsidian criterion)",
      "anchor": "12-working-with-humans-the-obsidian-criterion"
    },
    {
      "number": "13",
      "title": "Kinds \u2014 outcomes and profiles, one registry",
      "anchor": "13-kinds--outcomes-and-profiles-one-registry"
    },
    {
      "number": "14",
      "title": "Beats \u2014 the grouping layer above notebooks",
      "anchor": "14-beats--the-grouping-layer-above-notebooks"
    },
    {
      "number": "15",
      "title": "Tooling \u2014 the flip CLI",
      "anchor": "15-tooling--the-flip-cli"
    },
    {
      "number": "16",
      "title": "Integration contract",
      "anchor": "16-integration-contract"
    },
    {
      "number": "17",
      "title": "Exports (generated projections)",
      "anchor": "17-exports-generated-projections"
    },
    {
      "number": "18",
      "title": "Workspaces \u2014 many notebooks, one root",
      "anchor": "18-workspaces--many-notebooks-one-root"
    },
    {
      "number": "19",
      "title": "Open questions",
      "anchor": "19-open-questions"
    }
  ],
  "entities": [
    {
      "type": "Source",
      "id_prefix": "P# A# F# T# S#",
      "dir": "references/",
      "spec": "5",
      "summary": "An external artifact we captured, and our judgment of it.",
      "judgment": true,
      "keys": [
        "type",
        "id",
        "aliases",
        "title",
        "resource",
        "local",
        "grade",
        "independence",
        "support",
        "status"
      ],
      "observed_keys": [
        "aliases",
        "description",
        "generated",
        "grade",
        "id",
        "independence",
        "local",
        "notes",
        "status",
        "support",
        "title",
        "type"
      ]
    },
    {
      "type": "Claim",
      "id_prefix": "C#",
      "dir": "claims/",
      "spec": "7",
      "summary": "A discrete assertion, its sources, and how far it has earned trust.",
      "judgment": true,
      "keys": [
        "type",
        "id",
        "aliases",
        "description",
        "status",
        "load_bearing",
        "sources",
        "independent_corroboration",
        "first_asserted",
        "generated"
      ],
      "observed_keys": [
        "aliases",
        "description",
        "first_asserted",
        "generated",
        "id",
        "independent_corroboration",
        "load_bearing",
        "sources",
        "status",
        "type"
      ]
    },
    {
      "type": "Decision",
      "id_prefix": "D#",
      "dir": "decisions/",
      "spec": "7",
      "summary": "A resolved fork and \u2014 the payload \u2014 why it was resolved that way.",
      "judgment": false,
      "keys": [
        "type",
        "id",
        "aliases",
        "question",
        "alternatives_rejected",
        "generated"
      ],
      "observed_keys": [
        "aliases",
        "alternatives_rejected",
        "description",
        "generated",
        "id",
        "question",
        "type"
      ]
    },
    {
      "type": "Question",
      "id_prefix": "Q#",
      "dir": "questions/",
      "spec": "7",
      "summary": "Something that needs answering, re-posable without losing the earlier wording.",
      "judgment": false,
      "keys": [
        "type",
        "id",
        "aliases",
        "status",
        "generated"
      ],
      "observed_keys": [
        "aliases",
        "description",
        "generated",
        "id",
        "status",
        "type"
      ]
    },
    {
      "type": "Work Session",
      "id_prefix": "dated",
      "dir": "sessions/",
      "spec": "8",
      "summary": "One human or agent working episode: generated {by, at}, model, tools, outputs.",
      "judgment": false,
      "keys": [
        "type",
        "generated",
        "model",
        "tools",
        "started"
      ],
      "observed_keys": [
        "generated",
        "model",
        "started",
        "tools",
        "type"
      ]
    }
  ],
  "ledgers": [
    {
      "path": "sources/_provenance.jsonl",
      "spec": "5",
      "label": "Capture log",
      "summary": "One line per acquisition: url, local path, sha256, bytes, tool, strategy, actor. The fixity record."
    },
    {
      "path": "derived/_derivations.jsonl",
      "spec": "8",
      "label": "Derivation log",
      "summary": "Inputs to tool and parameters to outputs, with hashes. A deliberately small PROV profile."
    },
    {
      "path": "log/log.jsonl",
      "spec": "8",
      "label": "Work log",
      "summary": "Fetched X, ran Y, hit wall Z. The generated newest-first view is log.md at the bundle root."
    },
    {
      "path": "log/passed.jsonl",
      "spec": "8",
      "label": "Passed ledger",
      "summary": "Negative evidence \u2014 considered and rejected, with the reason. Prevents rediscovery loops."
    }
  ],
  "lifecycle": [
    {
      "stage": "captured",
      "act": "flip add-source",
      "spec": "5",
      "gains": "Local bytes in sources/raw/, hashed, with a provenance line.",
      "worth": "Custody. Nothing else \u2014 the page opens at grade ?."
    },
    {
      "stage": "judged",
      "act": "flip grade",
      "spec": "5",
      "gains": "grade, independence, freshness \u2014 recorded by a named actor after reading.",
      "worth": "Now it can count toward a claim. Ungraded sources corroborate nothing."
    },
    {
      "stage": "cited",
      "act": "flip claim add --source",
      "spec": "7",
      "gains": "An edge from a claim, and a regenerated citation block.",
      "worth": "The claim enters as asserted, whatever the source's grade."
    },
    {
      "stage": "corroborating",
      "act": "flip claim source add",
      "spec": "7",
      "gains": "independent_corroboration, recomputed from the judged sources present.",
      "worth": "Counted, never trusted from the page. Doctor flags drift."
    },
    {
      "stage": "verified",
      "act": "flip claim status \u2026 verified",
      "spec": "7",
      "gains": "The status, if and only if the profile's bar is met.",
      "worth": "Refused with a non-zero exit otherwise. Or earned by an adversarial or recomputation record."
    }
  ],
  "profiles": [
    {
      "id": "ledger",
      "intent": "Bibliography or source spine.",
      "requires": "references/"
    },
    {
      "id": "scout",
      "intent": "Screen an angle fast, editor lens active.",
      "requires": "hypotheses with falsifiers \u00b7 decisions/ \u00b7 passed ledger"
    },
    {
      "id": "research-review",
      "intent": "Question-organised survey, heading for publication.",
      "requires": "claims/ \u00b7 sessions/ \u00b7 drafts/ \u00b7 full custody"
    },
    {
      "id": "engagement",
      "intent": "Confidential client work.",
      "requires": "research-review + confidential policy + citation rule + HANDOFF.md"
    },
    {
      "id": "data-investigation",
      "intent": "Dataset-first reporting.",
      "requires": "derivation ledger \u00b7 ingest scripts \u00b7 frozen data contracts"
    },
    {
      "id": "pursuit",
      "intent": "One question under pursuit.",
      "requires": "questions/ \u00b7 claims/ \u00b7 a dated question plan with a stop rule"
    }
  ]
};
