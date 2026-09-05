# Keep a repeatable gain

Start with the user's problem and the useful change: "preserve spreadsheet
identifiers" or "pick up a discussion without missing later replies." A plugin
name is a packaging decision made after the work has something worth keeping.

1. **Name the recurring job.** Record what triggers it, who needs the result,
   and the avoidable work or error. Point to the source, decision or session
   that exposed it. An explicit request to share a process is also a reuse case;
   repetition is useful evidence, not an arbitrary minimum count.
2. **Solve one case.** Inspect installed lanes and existing public plugins.
   Use a maintained upstream tool where it fits; keep platform access and
   conversion in adapters, with custody and judgments in Flip. Preserve a
   small before/after example and what the successful command actually returned.
3. **Try another case.** Change something relevant: source shape, missing data,
   permissions, language or layout. Include the original failure in a regression
   fixture when appropriate. Compare the result with the old method on the same
   inputs. Record observed fewer repairs, preserved fields or saved steps;
   measure time only when measured. If the gain does not survive, narrow the
   proposed tool or retain the lesson without claiming general success.
4. **Keep it where the next user will find it.** Improve the existing plugin
   when the job fits. Otherwise choose the smallest extension with
   notebook-extend, and package with notebook-plugin-author when it should
   travel together. A lesson or a single workflow is a useful result too.
   Link the solution from the applicable source/audit/workflow skill so agents
   know when to get it. Include setup, a runnable example, expected output,
   failure behavior and remaining live checks. Private originals and credentials
   stay in their notebook/configuration; shared examples should be synthetic or
   deliberately cleared for sharing.

Keep a short entry in an existing author-owned `lessons.md` or decision page:

```markdown
### <problem the next person will recognize>
- When: <trigger and source/session pointers>
- Do: <working method and where to get it>
- Checked: <same-input before/after and another case; observed benefit>
- Limits: <failure cases and untested access or outcome>
- Reuse: <existing plugin, local definition, or next concrete change>
```

Append only the useful lesson; do not create a new tracking system, a required
scorecard or a plugin quota. Do not rewrite generated indexes or old ledger rows.
Use qualified notebook handles for cross-notebook entity references.

## Examples of useful changes

| Recurring problem | Smallest useful thing to keep | Check that matters |
|---|---|---|
| A workbook code loses leading zeros during Markdown conversion | Structured-cell adapter plus an interpretation skill | Original failure and another workbook preserve codes/coordinates; formula caches remain distinguishable |
| A thread's opening post is stale | Existing discussion adapter plus a refresh workflow | Later replies/state reach custody and change detection catches the relevant update |
| A transcript changes while audio stays identical | Fix the existing transcript plugin's bundle format | Actual Flip recheck detects the changed transcript with unchanged audio |
| Draft handoffs repeatedly omit evidence limitations | Handoff template and review workflow | A new reviewer can find supporting sources and unresolved items; rendering alone proves neither |

These examples show tests to run, not universal claims about tool availability.
A fixture pass establishes behavior on that fixture. Keep live access, successful
reuse and observed user benefit as separate statements. If sharing is requested,
prepare the runnable bundle and documentation; repository publication, package
publication and executable activation each retain their actual authorization.
