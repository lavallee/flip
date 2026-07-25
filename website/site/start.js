/* Start page: drop the real output of each step in beneath its commands.

   The outputs come from the same build-time CLI run that drives the flipbook,
   so the page cannot show a success message the tool no longer prints. */
(function () {
  "use strict";

  var book = window.__FLIP_BOOK__;
  var meta = window.__FLIP_META__;
  var kit = window.flipsite;
  if (!kit) return;

  if (meta) {
    document.querySelectorAll('[data-fact="python"]').forEach(function (node) {
      // ">=3.12" is a requirement expression; "3.12+" is a sentence.
      node.textContent = meta.requires_python.replace(/^>=\s*/, "") + "+";
    });
  }

  if (!book || !book.steps) return;

  function step(id) {
    return book.steps.filter(function (s) { return s.id === id; })[0] || null;
  }

  /** Show a step's stdout as the output of the command above it. */
  function output(hostId, stepId, caption) {
    var host = document.getElementById(hostId);
    var source = step(stepId);
    if (!host || !source || !source.stdout) return;
    host.appendChild(kit.record({
      path: "output",
      refused: source.refused,
      text: source.stdout,
      caption: caption
    }));
  }

  output("out-new", "new",
    "flip tells you what it made and what to do next. Every command that can leave "
    + "you unsure of the next move says so.");
  output("out-capture", "capture",
    "The id, where the bytes landed, the page it opened — and the grade it did not "
    + "assign, with the command that would.");
  output("out-grade", "grade",
    "Both axes, recorded against your actor.");
  output("out-refused", "refused",
    "The refusal names the shortfall, lists the sources it counted, and gives you "
    + "every legitimate route forward. Exit code 1.");
  output("out-doctor", "show",
    "The hot view: what is open, what needs work, and where you left off.");
})();
