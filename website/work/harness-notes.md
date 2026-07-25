# Harness and scaffolding notes — observed while building this site

Private working document. Not deployed. Written for pruning the operations
files, not for the flip repo's benefit.

Context: this build ran on Opus 5 in Claude Code, in an environment carrying
85 installed skills, most written for prior-generation models. What follows is
only what actually bit or would have bitten — not a general audit.

## 1. Three overlapping design stacks, no router between them

`~/.claude/skills` currently holds **three independent design-review lineages**:

| Lineage | Skills | Origin |
|---|---|---|
| gstack | `design-review`, `design-html`, `design-consultation`, `design-shotgun`, `plan-design-review`, `plan-ceo-review`, `plan-eng-review`, `plan-devex-review`, `autoplan`, `devex-review`, `review` | prior-gen |
| forge | `forge-review-design`, `forge-review-ceo`, `forge-review-eng`, `forge-review-dx`, `forge-review-all`, `forge-plan`, `forge-orient`, `forge-architect`, `forge-itemize` | newer |
| des | `PRACTICE.md`, `modes/`, `RUBRIC.md`, `SKILL.md` in the des repo — **not installed as a skill at all** | current |

The one I was asked to use is the one that is not installed. I read it out of
the des repo directly, which worked, but nothing in the environment would have
led me there — `design-review` and `forge-review-design` both advertise
themselves for exactly this task and neither knows DES exists.

`plan-ceo-review` / `plan-design-review` / `plan-eng-review` / `plan-devex-review`
are near-duplicates of the four `forge-review-*` skills. `autoplan` and
`forge-review-all` are the same idea twice.

**Suggested:** install des as a skill (its `SKILL.md` is written for exactly
this and says it is drop-in). Retire the `plan-*-review` quartet in favour of
`forge-review-*`. Retire `autoplan` in favour of `forge-review-all`. If DES is
the house design practice, `design-review` and `design-html` should either
delegate to it or go.

## 2. Instructions written against a weaker model's failure modes

Two standing instructions in the environment read as guardrails against
prior-generation over-eagerness:

- *"Do not call the AgentTool unless the user requested it"*
- *"Do not use workflows or deep-research unless the user requested it"*

Both were correct here — this was single-threaded work — so nothing was lost.
But they are blanket prohibitions where the underlying concern is cost and
surprise, not capability. Worth reconsidering whether the rule should be
"don't fan out silently" rather than "don't fan out."

Note also that the memory file records the 0.3–0.9 releases as being built
with **Fable 5 workflows of 5–11 agents with an adversarial reviewer**, and
credits that pattern with finding 10, 12, and 4 confirmed bugs. That is a
documented, effective practice for this repo that the current standing
instruction forbids by default. Those two positions should be reconciled
deliberately rather than left in tension.

## 3. The gstack skill set assumes infrastructure this task did not use

`browse`, `benchmark`, `canary`, `pair-agent`, `connect-chrome`,
`setup-browser-cookies`, `_gstack-command` all assume the gstack browse daemon.
The Playwright MCP was present and worked fine. Two browser stacks, and the
skill descriptions do not distinguish when to use which.

One concrete friction: Playwright MCP **blocks `file://`**, while artoo's core
contract is that an artifact must render from a `file://` URL. I had to run a
local HTTP server to do visual QA on a property that is specifically about not
needing a server. Worth a note in whichever browser skill survives.

## 4. Skill descriptions that trigger on the wrong signal

`claude-api` has an aggressive trigger: *"read BEFORE opening the target file …
whenever the prompt names Claude/Anthropic in any form (Claude, Anthropic,
Fable, Opus, Sonnet, Haiku, `claude-*`)"*. This task named `claude-opus-5` as
demo data in a `flip session start --model` example, and the receipt records
the served model. Neither has anything to do with the Claude API. The trigger
matches strings, not intent.

`omarchy` is marked **REQUIRED** for any edit under `~/.config/*` — a strong
word for a rule that has nothing to do with this project.

## 5. Version drift between installed tools and their repos

Not scaffolding, but it cost real time at the start and will recur:

- installed `flip` was **0.9.0**, repo at **0.10.0**
- installed `artoo` was **0.1.0**, repo at **0.2.0**

The site's whole premise — `flip export json` feeding artoo's provenance panel
— exists only in the newer pair. Both had to be reinstalled from local source
before anything worked. Since these tools are developed in this workspace and
consumed here too, a `uv tool install --force ./<repo>` step after each release
(or a documented "dogfood install" convention) would remove the trap.

## 6. What worked well and should not be touched

- **artoo's DES-governed scaffold.** `artoo init` stamping a design brief with
  reader decision, counter-reading, licit comparisons, and proof required —
  before any markup exists — did more to shape this site than any review skill
  would have. The brief's anti-references were load-bearing at implementation
  time, not decoration.
- **The private-file firewall.** `work/` and `notebook/` sitting beside `site/`
  and being structurally unable to ship is exactly right for a public repo, and
  it meant the research could stay candid.
- **DES's decision stack** (`PRACTICE.md` §1). Forcing "observed user behaviour:
  weak, and unfixable by design" to the surface early is what produced the
  site's honest posture instead of a fabricated one. This is the piece of the
  new model that earned its place most clearly.
- **The audience/task-before-style rule.** Choosing the reader first made the
  IA fall out almost mechanically.

## 7. Gap in the new des model, offered as feedback

DES has strong vocabulary for *modes*, *dials*, and *fingerprints*, and a good
decision stack. What it does not have is a template for the **customer
analysis** and **IA** artifacts themselves — `PRACTICE.md` §3's design plan has
one line for "user and task," which is not enough for a multi-route site with
three distinct reader populations.

I wrote `work/ia.md` to fill that gap: a reader table (arrives-from, job in
their words, what convinces, what loses them), the marked decision stack, then
per-route mode + dials + task anatomy + structural fingerprint + what is
deliberately absent. If that shape is useful it could become a scaffolded
artifact next to the design brief, the way artoo already scaffolds the brief.
