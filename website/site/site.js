/* flip site — shared behaviour. No dependencies, file:// safe.

   Everything here is progressive enhancement over markup that already works:
   copy buttons appear only if the clipboard API exists, and the data-driven
   records replace a static fallback only once the generated data has loaded. */
(function () {
  "use strict";

  // -- copy buttons on command lines ---------------------------------------
  // Added by script so a reader without clipboard support never sees a
  // control that cannot do anything (no dead affordances). Idempotent, so
  // pages that swap in new command lines can call it again.
  function enhance() {
    if (!navigator.clipboard || window.isSecureContext === false) return;
    document.querySelectorAll(".cmd").forEach(function (cmd) {
      if (cmd.querySelector(".copy")) return;
      var code = cmd.querySelector("code");
      if (!code) return;
      var button = document.createElement("button");
      button.type = "button";
      button.className = "copy";
      button.textContent = "copy";
      button.setAttribute("aria-label", "Copy command: " + code.textContent);
      button.addEventListener("click", function () {
        navigator.clipboard.writeText(code.textContent).then(function () {
          button.textContent = "copied";
          button.setAttribute("data-copied", "yes");
          window.setTimeout(function () {
            button.textContent = "copy";
            button.removeAttribute("data-copied");
          }, 1600);
        }, function () {
          button.textContent = "press ⌘C";
        });
      });
      cmd.appendChild(button);
    });
  }

  enhance();

  // -- shared helpers exposed to the page scripts ---------------------------
  window.flipsite = {
    /** Attach copy buttons to any command lines added since the last call. */
    enhance: enhance,

    /** Escape text destined for innerHTML. */
    esc: function (text) {
      return String(text == null ? "" : text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
    },

    /** Render text with `backticked` spans as real code elements. */
    codeify: function (text) {
      var fragment = document.createDocumentFragment();
      var pattern = /`([^`]+)`/g;
      var last = 0;
      var match;
      while ((match = pattern.exec(text))) {
        if (match.index > last) {
          fragment.appendChild(document.createTextNode(text.slice(last, match.index)));
        }
        var code = document.createElement("code");
        code.textContent = match[1];
        fragment.appendChild(code);
        last = match.index + match[0].length;
      }
      fragment.appendChild(document.createTextNode(text.slice(last)));
      return fragment;
    },

    /** Build the standard record block: chip, literal content, caption. */
    record: function (options) {
      var wrap = document.createElement("div");
      wrap.className = "record" + (options.refused ? " record--refused" : "");

      var chip = document.createElement("div");
      chip.className = "record__chip";
      var path = document.createElement("strong");
      path.textContent = options.path || "";
      chip.appendChild(path);
      if (options.label) {
        chip.appendChild(document.createTextNode(options.label));
      }
      if (options.truncated) {
        var more = document.createElement("span");
        more.textContent = "· truncated";
        chip.appendChild(more);
      }
      wrap.appendChild(chip);

      var pre = document.createElement("pre");
      var code = document.createElement("code");
      code.textContent = options.text || "";
      pre.appendChild(code);
      wrap.appendChild(pre);

      if (options.caption) {
        var caption = document.createElement("p");
        caption.className = "record__caption";
        caption.textContent = options.caption;
        wrap.appendChild(caption);
      }
      return wrap;
    },

    /** Link into the spec at a numbered section. */
    specHref: function (number, sections) {
      var match = (sections || []).filter(function (s) { return s.number === String(number); })[0];
      var base = "https://github.com/lavallee/flip/blob/main/SPEC.md";
      return match ? base + "#" + match.anchor : base;
    },

    specLabel: function (number, sections) {
      var match = (sections || []).filter(function (s) { return s.number === String(number); })[0];
      return match ? "SPEC §" + match.number + " " + match.title.replace(/`/g, "") : "SPEC";
    }
  };
})();
