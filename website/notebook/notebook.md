---
type: Notebook
description: flip site — claims and their sources
---

# Reporter's notebook — flip site — claims and their sources

## The tip

The flip documentation site makes load-bearing claims about flip. This
notebook holds the sources behind them, so a reader who does not take our
word for it can check.

It exists mainly to be checked. A project whose argument is "keep custody of
what you rely on" has no business publishing a site that cites nothing, and
the site's provenance panel is generated from this notebook by
`flip export json` at build time — so if this ledger is thin or stale, the
site says so on every page.

**What is deliberately visible here:**

- **C5 is `unconfirmed`.** That lineage discipline makes research cheaper to
  reuse later is the project's north-star bet. No adoption evidence has been
  captured because none exists. It is recorded as a claim so that it is
  visible as an unmet one, not quietly dropped from the argument.
- **C4 was downgraded by hand.** It passed the verification gate on flip's
  own grade-A specification with zero independent corroboration. That is
  legal — a grade-A primary clears the default bar — but the Admiralty
  lineage is a claim about the outside world, and our own spec asserting it
  is not evidence of it. Downgraded to `needs-2nd`. The gate is a floor, not
  a ceiling, and a maintainer overriding it downward is the system working.
- **F1 is graded `self-interested`.** flip's SPEC.md is the authoritative
  primary for what flip specifies, and an interested party on whether flip is
  a good idea. Both are true and the two axes are what let us say so.

## Sources & provenance

Three captured sources, all held locally with hashes in
`sources/_provenance.jsonl`:

- **F1 · flip SPEC.md** — first-party, the format's own specification at the
  site's build revision. Grade A, self-interested.
- **F2 · flip pyproject.toml** — first-party package metadata. Grade A,
  original: a dependency list is not an assertion about the world, it is the
  artifact.
- **A1 · OKF v0.1 SPEC.md** — the Open Knowledge Format specification from
  its own publisher, Apache-2.0, fetched over the network with the bundled
  `flip-fetch` helper. Grade B, original. This is the only source here that
  is independent of flip, and it is what makes C3 worth more than an
  assertion.

Custody note: the two first-party captures record an absolute `file://` URL
in the provenance ledger, because that is where the bytes came from on the
machine that built the site. The ledger is append-only and has not been
rewritten to look tidier.
