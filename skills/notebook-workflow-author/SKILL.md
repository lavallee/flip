---
name: notebook-workflow-author
description: Turn an expert's reusable sequence of research work into a small validated Flip workflow with inspectable phase outputs and a tiny receipt-backed example.
---

# notebook-workflow-author

Interview in the expert's language. Their sequence and stopping judgment are
the content; your job is to express it as one plain TOML workflow without
inventing rigor or a general work graph.

1. Run `flip workflow list` and inspect the closest definition with `flip
   workflow show <id>`. Fork it with `flip workflow new <id> --from <id>` when
   the shape is close.
2. Ask what starts a pass, what visibly changes at each stage, and how a later
   worker knows where to resume. Use 2–6 phases. Each phase gets an imperative
   guide and concrete `produces` receipts.
3. Ask which transitions are binary. Keep judgment calls in the guide; do not
   fake machine-checkability or add an expression language. `next` is a
   suggestion, never execution.
4. Decide whether the terminal phase stops or loops to the entry phase. The
   human or harness still applies the mission's stop condition.
5. Run `flip workflow check <path>`, pin it in a disposable notebook with
   `flip workflow use <id>`, and exercise at least two phase receipts using
   `flip session start --workflow ... --phase ... --item ...` and `flip
   session end --output ... --check ...`.
6. Inspect `flip workflow next --explain` and the session frontmatter. Include
   the tiny walkthrough beside a shared workflow.

Keep workflow identity independent of kind: one outcome may use several
maintenance processes, and one process may serve several outcomes. If the
request also needs a portable bundle, pass the validated definition to the
notebook-plugin-author procedure.
