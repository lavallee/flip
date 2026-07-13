---
name: notebook-source
description: Capture and grade a source with custody discipline — invoke every time the work starts relying on an external artifact (URL, DOI, file, dataset, transcript).
---

# notebook-source

Custody first: local bytes, hash, provenance, then judgment. A source you
didn't capture is a source you don't have.

## Checklist

1. **Capture the moment you rely on it.**
   ```bash
   flip add-source <url|doi:...|path> --note "<why captured / anything odd about the get>"
   ```
   flip infers the kind (web/paper/file, plus social for X/Twitter post URLs);
   pass `--kind` for datasets, talks, or anything ambiguous. Raw bytes land
   in `sources/raw/`, the hash in the provenance ledger, and a source page
   opens at `references/<slug>.md` at
   grade `?` — the id (`A3`, `F1`, …) is in its frontmatter and `flip open
   <id>` finds it again. URL/DOI capture runs the fetcher configured in
   `$FLIP_HOME/config.toml` — if flip errors, add the stanza it prints; never
   work around the fetcher by saving text yourself.
   On a workstation with the fleet lanes configured, ordinary URLs route to
   Downunder, X/Twitter posts to Jackdaw, and DOI/arXiv identifiers to
   Paperboy.
2. **Chase the original.** Before grading, check whether this is the original
   or a republisher/derivative. If it republishes, capture the original too
   and grade the republisher accordingly — republishers and derivatives do
   not count toward claim corroboration.
3. **Read it, then grade it** (grading is a judgment made after reading, not
   a formality at capture):
   ```bash
   flip grade <id> --grade A|B|C --independence original|republisher|derivative|self-interested \
       --freshness fresh|dated --notes "<why this grade>"
   ```
   `A` authoritative primary (gov / peer-reviewed / data extracted
   ourselves) · `B` official docs, independent journalism · `C` vendor,
   practitioner, self-interested, or any LLM/retrieval synthesis. Flag
   `--freshness dated` when older than the profile's threshold (~18 months).
   A source left at grade `?` counts toward nothing — it cannot corroborate
   a claim until judged. `flip source list` shows every capture's
   grade/independence/freshness at a glance; sweep it for `?` rows before
   any claim audit.
4. **Public-terminus check.** If the manifest's `citation_rule` is
   `public-terminus`, confirm any load-bearing chain this source joins ends
   at a public, independently verifiable source — a grade-C intermediary
   can't be the terminus.
5. **Wire it in.** Link the source to the claims it backs
   (`flip claim add ... --source <id>` or update existing claims), and cite
   it in prose as `[A3]`. Put pull-quotes, misgivings, and capture notes in
   the source page's body — when editing the page, change only what you
   mean to and preserve frontmatter keys you don't own. Log anything notable
   about the capture with `flip log`.

For quick discovery, Trawler may be configured as the `lookup` kind:
`flip add-source --kind lookup "<question>"`. Its cited synthesis is a lead,
not corroboration: read it, grade it C, and separately capture and judge the
public URLs in its citations before relying on any claim.

Do not paste fetched text into the notebook as if it were a source — every
source enters through `flip add-source` so raw bytes, hash, and provenance
are on record; prose citing no source id is opinion. And never `mv` a source
page: `flip rename <id> <new-slug>` is the only sanctioned rename.
