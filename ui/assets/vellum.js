(function () {
  "use strict";
  if (window.VellumContext) return;

  const ROOT_ID = "vellum-context";
  let current = null;
  let expanded = false;
  let initialized = false;
  let stats = null;
  let statsRequestedFor = null;

  function rememberedExpanded() {
    try {
      return window.localStorage.getItem("vellum-context-expanded") === "true";
    } catch (_error) {
      return false;
    }
  }

  function rememberExpanded(value) {
    try {
      window.localStorage.setItem("vellum-context-expanded", String(value));
    } catch (_error) {
      // Some hardened WebViews disable storage; the current review still works.
    }
  }

  function setExpanded(value) {
    expanded = Boolean(value);
    if (current && current.defaultState === "remember") rememberExpanded(expanded);
  }

  function send(message) {
    if (typeof pycmd === "function") pycmd(message);
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function ensureRoot() {
    let root = document.getElementById(ROOT_ID);
    if (root) return root;
    root = element("aside", "vellum-context");
    root.id = ROOT_ID;
    root.setAttribute("aria-label", "Vellum topic context");
    root.innerHTML =
      '<button class="vellum-context__toggle" type="button" aria-expanded="false">' +
      '<span class="vellum-context__chevron" aria-hidden="true">‹</span>' +
      '<span class="vellum-context__compact"></span></button>' +
      '<div class="vellum-context__panel"></div>';
    root.querySelector(".vellum-context__toggle").addEventListener("click", function () {
      send("vellum:toggle_sidebar");
    });
    document.body.appendChild(root);
    return root;
  }

  function render(payload) {
    if (!current || current.topicId !== payload.topicId) {
      stats = null;
      statsRequestedFor = null;
    }
    current = payload;
    const root = ensureRoot();
    root.dataset.side = payload.side === "left" ? "left" : "right";
    root.dataset.theme = payload.theme || "auto";
    root.style.setProperty("--vellum-context-width", String(payload.width || 288) + "px");
    root.classList.toggle("vellum-reduced-motion", Boolean(payload.reducedMotion));
    const wasInitialized = initialized;
    if (!initialized) {
      expanded = payload.defaultState === "remember"
        ? rememberedExpanded()
        : payload.defaultState === "expanded";
      initialized = true;
    }
    if (payload.pinned) {
      setExpanded(true);
    } else if (
      wasInitialized &&
      payload.phase === "reviewQuestion" &&
      payload.autoCollapse
    ) {
      setExpanded(false);
    }
    root.classList.toggle("is-expanded", expanded);

    const toggle = root.querySelector(".vellum-context__toggle");
    toggle.setAttribute("aria-expanded", String(expanded));
    root.querySelector(".vellum-context__compact").textContent = payload.path.length
      ? payload.path[0] + " · " + payload.title
      : "No topic";

    const panel = root.querySelector(".vellum-context__panel");
    panel.replaceChildren();
    if (payload.showTitle) {
      panel.appendChild(element("div", "vellum-context__eyebrow", "Current topic"));
      panel.appendChild(element("h2", "vellum-context__title", payload.title));
    }

    if (!payload.topicId) {
      const empty = element(
        "p",
        "vellum-context__empty",
        "No topic hierarchy was found for this card."
      );
      panel.appendChild(empty);
      const configure = element(
        "button",
        "vellum-context__configure",
        "Configure topic roots →"
      );
      configure.type = "button";
      configure.addEventListener("click", function () {
        send("vellum:configure_topics");
      });
      panel.appendChild(configure);
    }

    if (payload.showBreadcrumbs && payload.path.length) {
      const nav = element("nav", "vellum-context__breadcrumbs");
      nav.setAttribute("aria-label", "Topic hierarchy");
      const ids = payload.ancestorIds.concat(payload.topicId || []);
      payload.path.forEach(function (label, index) {
        const button = element("button", "vellum-context__crumb", label);
        button.type = "button";
        button.addEventListener("click", function () {
          if (ids[index]) send("vellum:open_topic:" + ids[index]);
        });
        nav.appendChild(button);
      });
      nav.addEventListener("keydown", function (event) {
        if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
        const crumbs = Array.from(nav.querySelectorAll("button"));
        const currentIndex = crumbs.indexOf(document.activeElement);
        if (currentIndex < 0) return;
        const step = event.key === "ArrowDown" ? 1 : -1;
        const next = Math.max(0, Math.min(crumbs.length - 1, currentIndex + step));
        if (next === currentIndex) return;
        event.preventDefault();
        crumbs[next].focus();
      });
      panel.appendChild(nav);
    }

    if (payload.sourceBadges.length) {
      const badges = element("div", "vellum-context__badges");
      payload.sourceBadges.forEach(function (label) {
        badges.appendChild(element("span", "vellum-context__badge", label));
      });
      panel.appendChild(badges);
    }

    const details = element("div", "vellum-context__details");
    if (stats) {
      if (payload.showCardCount) {
        details.appendChild(
          element(
            "div",
            "vellum-context__count",
            stats.total + (stats.total === 1 ? " card" : " cards")
          )
        );
      }
      if (payload.showMaturityBreakdown) {
        const breakdown = element("div", "vellum-context__breakdown");
        breakdown.appendChild(element("span", "", "Mature " + stats.mature));
        breakdown.appendChild(element("span", "", "Learning " + stats.learning));
        breakdown.appendChild(element("span", "", "New " + stats.new));
        details.appendChild(breakdown);
      }
      if (payload.showRetention && stats.retention != null && stats.recentReviews > 0) {
        const retention = element(
          "div",
          "vellum-context__retention",
          Math.round(stats.retention * 100) + "% recent retention"
        );
        retention.title = "Based on the last 50 rated reviews in this topic.";
        details.appendChild(retention);
      }
      if (payload.showRecentFailures && stats.recentFailures > 0) {
        details.appendChild(
          element("div", "vellum-context__failures", stats.recentFailures + " cards recently failed")
        );
      }
      if (payload.showHealth && stats.health) {
        const health = element("div", "vellum-context__health", "Topic Health · " + stats.health);
        health.dataset.state = stats.health.toLowerCase().replace(/\s+/g, "-");
        health.title = (stats.healthReason ? stats.healthReason + " " : "") +
          "This is a workflow heuristic, not a mastery score.";
        details.appendChild(health);
      }
    } else if (payload.topicId) {
      details.appendChild(element("div", "vellum-context__loading", "Loading topic details…"));
    }
    panel.appendChild(details);

    if (payload.showRecovery && payload.topicId) {
      const recover = element("button", "vellum-context__recover", "Recover Topic");
      recover.type = "button";
      recover.addEventListener("click", function () {
        send("vellum:recover:" + payload.topicId);
      });
      panel.appendChild(recover);
    }

    if (expanded && payload.topicId && !stats && statsRequestedFor !== payload.topicId) {
      statsRequestedFor = payload.topicId;
      send("vellum:context_stats:" + payload.topicId);
    }
  }

  function updateEncoded(encoded) {
    try {
      const bytes = Uint8Array.from(atob(encoded), function (char) {
        return char.charCodeAt(0);
      });
      render(JSON.parse(new TextDecoder().decode(bytes)));
    } catch (error) {
      console.warn("Vellum Context payload rejected", error);
    }
  }

  function updateStatsEncoded(encoded) {
    try {
      const bytes = Uint8Array.from(atob(encoded), function (char) {
        return char.charCodeAt(0);
      });
      stats = JSON.parse(new TextDecoder().decode(bytes));
      statsRequestedFor = current ? current.topicId : null;
      if (current) render(current);
    } catch (error) {
      console.warn("Vellum Context stats rejected", error);
    }
  }

  window.VellumContext = {
    updateEncoded: updateEncoded,
    updateStatsEncoded: updateStatsEncoded,
    toggle: function () {
      setExpanded(!expanded);
      if (current) render(current);
    },
    remove: function () {
      const root = document.getElementById(ROOT_ID);
      if (root) root.remove();
      current = null;
      stats = null;
      statsRequestedFor = null;
      initialized = false;
    },
  };

  function matchesConfiguredShortcut(event, configuredShortcut) {
    const pieces = String(configuredShortcut)
      .split("+")
      .map(function (piece) { return piece.trim().toLowerCase(); })
      .filter(Boolean);
    if (!pieces.length) return false;
    const required = {
      alt: pieces.includes("alt") || pieces.includes("option"),
      ctrl: pieces.includes("ctrl") || pieces.includes("control"),
      meta: pieces.includes("meta") || pieces.includes("cmd") || pieces.includes("command"),
      shift: pieces.includes("shift"),
    };
    if (
      Boolean(event.altKey) !== required.alt ||
      Boolean(event.ctrlKey) !== required.ctrl ||
      Boolean(event.metaKey) !== required.meta ||
      Boolean(event.shiftKey) !== required.shift
    ) return false;
    const keyPiece = pieces.find(function (piece) {
      return !["alt", "option", "ctrl", "control", "meta", "cmd", "command", "shift"]
        .includes(piece);
    });
    if (!keyPiece) return false;
    const aliases = { esc: "escape", space: " " };
    const expected = aliases[keyPiece] || keyPiece;
    return String(event.key).toLowerCase() === expected;
  }

  document.addEventListener("keydown", function (event) {
    if (!expanded || !current || !current.collapseShortcut) return;
    const target = event.target;
    if (target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName)) return;
    if (!matchesConfiguredShortcut(event, current.collapseShortcut)) return;
    event.preventDefault();
    setExpanded(false);
    render(current);
  });
})();

(function () {
  "use strict";
  if (window.VellumMindNotes) return;

  function send(message) {
    if (typeof pycmd === "function") pycmd(message);
  }

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function root() {
    let element = document.getElementById("vellum-mind-notes");
    if (element) return element;
    element = node("aside", "vellum-mind-notes");
    element.id = "vellum-mind-notes";
    element.setAttribute("aria-label", "Vellum Mind Notes");
    element.setAttribute("aria-live", "polite");
    document.body.appendChild(element);
    return element;
  }

  function render(payload) {
    const panel = root();
    panel.dataset.theme = payload.theme || "auto";
    panel.classList.toggle("vellum-reduced-motion", Boolean(payload.reducedMotion));
    panel.replaceChildren();
    if (!payload.topicId || !payload.notes.length) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    panel.appendChild(node("div", "vellum-mind-notes__topic", payload.topicLabel));
    payload.notes.forEach(function (note) {
      const item = node("section", "vellum-mind-notes__item");
      item.appendChild(node("div", "vellum-mind-notes__age", "FROM YOU · " + note.age.toUpperCase()));
      item.appendChild(node("p", "vellum-mind-notes__body", note.body));
      const resolve = node("button", "vellum-mind-notes__resolve", "Mark resolved");
      resolve.type = "button";
      resolve.addEventListener("click", function () {
        send("vellum:mind-note:resolve:" + note.id);
      });
      item.appendChild(resolve);
      panel.appendChild(item);
    });
    const add = node("button", "vellum-mind-notes__add", "Add another note");
    add.type = "button";
    add.addEventListener("click", function () { send("vellum:mind-note:add"); });
    panel.appendChild(add);
  }

  window.VellumMindNotes = {
    updateEncoded: function (encoded) {
      try {
        const bytes = Uint8Array.from(atob(encoded), function (char) {
          return char.charCodeAt(0);
        });
        render(JSON.parse(new TextDecoder().decode(bytes)));
      } catch (error) {
        console.warn("Vellum Mind Notes payload rejected", error);
      }
    },
    remove: function () {
      const panel = document.getElementById("vellum-mind-notes");
      if (panel) panel.remove();
    },
  };
})();

(function () {
  "use strict";
  if (window.VellumDebriefHome) return;

  const ROOT_ID = "vellum-debrief-home";

  function send(message) {
    if (typeof pycmd === "function") pycmd(message);
  }

  function decode(encoded) {
    const bytes = Uint8Array.from(atob(encoded), function (char) {
      return char.charCodeAt(0);
    });
    return JSON.parse(new TextDecoder().decode(bytes));
  }

  function button(label, message, primary) {
    const value = document.createElement("button");
    value.type = "button";
    value.className = primary ? "vellum-debrief-card__primary" : "vellum-debrief-card__quiet";
    value.textContent = label;
    value.addEventListener("click", function () { send(message); });
    return value;
  }

  function formatDuration(seconds) {
    const safe = Math.max(0, Number(seconds) || 0);
    if (safe < 60) return Math.round(safe) + "s";
    const minutes = Math.floor(safe / 60);
    const remainder = Math.round(safe % 60);
    return remainder ? minutes + "m " + String(remainder).padStart(2, "0") + "s" : minutes + "m";
  }

  function ensureRoot() {
    let root = document.getElementById(ROOT_ID);
    if (root) return root;
    root = document.createElement("section");
    root.id = ROOT_ID;
    root.className = "vellum-debrief-home";
    root.setAttribute("aria-label", "Vellum session continuity");
    const home = document.getElementById("vellum-home");
    if (home && home.parentNode) home.parentNode.insertBefore(root, home);
    else document.body.appendChild(root);
    return root;
  }

  function render(payload) {
    const root = ensureRoot();
    root.replaceChildren();
    root.classList.toggle("vellum-reduced-motion", Boolean(payload.reducedMotion));
    if (payload.completion) {
      const value = payload.completion;
      const card = document.createElement("article");
      card.className = "vellum-debrief-card vellum-debrief-card--complete";
      const eyebrow = document.createElement("div");
      eyebrow.className = "vellum-debrief-card__eyebrow";
      eyebrow.textContent = "SESSION COMPLETE";
      const title = document.createElement("h2");
      title.textContent = value.cards + (value.cards === 1 ? " card reviewed" : " cards reviewed");
      const metrics = document.createElement("p");
      metrics.className = "vellum-debrief-card__metrics";
      metrics.textContent = formatDuration(value.seconds) + " active · " + value.again + " Again · " + value.hard + " Hard";
      const next = document.createElement("p");
      next.textContent = value.suggestion;
      const actions = document.createElement("div");
      actions.className = "vellum-debrief-card__actions";
      actions.appendChild(button("Open Debrief", "vellum:debrief:open:" + value.sessionId, true));
      actions.appendChild(button("Dismiss", "vellum:debrief:dismiss:" + value.sessionId, false));
      card.append(eyebrow, title, metrics, next, actions);
      root.appendChild(card);
    }
    if (payload.handoff) {
      const value = payload.handoff;
      const card = document.createElement("article");
      card.className = "vellum-debrief-card vellum-debrief-card--handoff";
      const eyebrow = document.createElement("div");
      eyebrow.className = "vellum-debrief-card__eyebrow";
      eyebrow.textContent = "FROM YOUR LAST SESSION";
      const text = document.createElement("p");
      text.className = "vellum-debrief-card__handoff";
      text.textContent = value.text;
      card.append(eyebrow, text, button("Mark Done", "vellum:handoff:done:" + value.sessionId, false));
      root.appendChild(card);
    }
    root.hidden = !payload.completion && !payload.handoff;
  }

  window.VellumDebriefHome = {
    updateEncoded: function (encoded) {
      try { render(decode(encoded)); }
      catch (error) { console.warn("Vellum Debrief payload rejected", error); }
    },
    remove: function () {
      const root = document.getElementById(ROOT_ID);
      if (root) root.remove();
    },
  };
})();

(function () {
  "use strict";
  if (window.VellumOnboardingInvite) return;
  const ROOT_ID = "vellum-onboarding-invite";

  function send(message) {
    if (typeof pycmd === "function") pycmd(message);
  }

  function decode(encoded) {
    const bytes = Uint8Array.from(atob(encoded), function (char) {
      return char.charCodeAt(0);
    });
    return JSON.parse(new TextDecoder().decode(bytes));
  }

  function render(payload) {
    let root = document.getElementById(ROOT_ID);
    if (!root) {
      root = document.createElement("section");
      root.id = ROOT_ID;
      root.className = "vellum-onboarding-invite";
      const home = document.getElementById("vellum-home");
      if (home && home.parentNode) home.parentNode.insertBefore(root, home);
      else document.body.appendChild(root);
    }
    root.replaceChildren();
    const copy = document.createElement("div");
    const eyebrow = document.createElement("div");
    eyebrow.className = "vellum-debrief-card__eyebrow";
    eyebrow.textContent = "WHAT’S NEW";
    const title = document.createElement("h2");
    title.textContent = payload.title;
    const text = document.createElement("p");
    text.textContent = payload.copy;
    copy.append(eyebrow, title, text);
    const actions = document.createElement("div");
    actions.className = "vellum-debrief-card__actions";
    const start = document.createElement("button");
    start.type = "button";
    start.className = "vellum-debrief-card__primary";
    start.textContent = "Start Tour";
    start.addEventListener("click", function () { send("vellum:onboarding:start"); });
    const later = document.createElement("button");
    later.type = "button";
    later.className = "vellum-debrief-card__quiet";
    later.textContent = "Not Now";
    later.addEventListener("click", function () { send("vellum:onboarding:not-now"); });
    actions.append(start, later);
    root.append(copy, actions);
  }

  window.VellumOnboardingInvite = {
    updateEncoded: function (encoded) {
      try { render(decode(encoded)); }
      catch (error) { console.warn("Vellum onboarding payload rejected", error); }
    },
    remove: function () {
      const root = document.getElementById(ROOT_ID);
      if (root) root.remove();
    },
  };
})();

(function () {
  "use strict";
  if (window.VellumOverview) return;

  window.VellumOverview = {
    updateEncoded: function (encoded) {
      try {
        const bytes = Uint8Array.from(atob(encoded), function (char) {
          return char.charCodeAt(0);
        });
        const payload = JSON.parse(new TextDecoder().decode(bytes));
        const target = document.getElementById("vellum-overview-estimate");
        if (target) {
          target.textContent = payload.cards
            ? payload.cards + " due · about " + payload.minutes + " min"
            : "No cards are currently due.";
        }
      } catch (error) {
        console.warn("Vellum Overview payload rejected", error);
      }
    },
  };
})();

(function () {
  "use strict";
  if (window.VellumHome) return;

  function send(message) {
    if (typeof pycmd === "function") pycmd(message);
  }

  function node(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    return element;
  }

  function ensureRoot() {
    let root = document.getElementById("vellum-home");
    if (root) return root;
    root = node("section", "vellum-home");
    root.id = "vellum-home";
    root.setAttribute("aria-label", "Vellum study continuity");
    document.body.appendChild(root);
    return root;
  }

  function render(payload) {
    const root = ensureRoot();
    root.dataset.theme = payload.theme || "auto";
    root.classList.toggle("vellum-reduced-motion", Boolean(payload.reducedMotion));
    root.replaceChildren();
    if (payload.greeting) root.appendChild(node("h2", "vellum-home__greeting", payload.greeting));

    const workload = node("section", "vellum-home__workload");
    workload.appendChild(
      node(
        "strong",
        "",
        String(payload.due) + (payload.due === 1 ? " card due" : " cards due")
      )
    );
    if (payload.showEstimatedWorkload) {
      workload.appendChild(node("span", "", "About " + payload.estimatedMinutes + " min"));
    }
    root.appendChild(workload);

    if (payload.showContinue && payload.resume) {
      const card = node("section", "vellum-home__card");
      card.appendChild(node("div", "vellum-home__eyebrow", "CONTINUE"));
      card.appendChild(node("h3", "", payload.resume.deck));
      const progress = payload.resume.total == null
        ? String(payload.resume.reviewed) + " reviewed"
        : payload.resume.reviewed + " / " + payload.resume.total;
      card.appendChild(node("p", "", progress));
      if (payload.resume.remaining != null) {
        const time = payload.resume.remainingMinutes == null
          ? ""
          : " · about " + payload.resume.remainingMinutes + " min";
        card.appendChild(
          node("p", "vellum-home__muted", payload.resume.remaining + " remaining" + time)
        );
      }
      if (payload.resume.lastTopic) {
        card.appendChild(
          node("p", "vellum-home__muted", "Last topic · " + payload.resume.lastTopic)
        );
      }
      const button = node("button", "vellum-home__action", "Resume →");
      button.type = "button";
      button.addEventListener("click", function () { send("vellum:home:resume"); });
      card.appendChild(button);
      root.appendChild(card);
    }

    if (payload.showTimeMachine && payload.presets.length) {
      const block = node("section", "vellum-home__card");
      block.appendChild(node("div", "vellum-home__eyebrow", "START A SESSION"));
      const buttons = node("div", "vellum-home__presets");
      payload.presets.forEach(function (minutes) {
        const button = node("button", "", minutes + "m");
        button.type = "button";
        button.addEventListener("click", function () { send("vellum:home:time:" + minutes); });
        buttons.appendChild(button);
      });
      const custom = node("button", "", "Custom…");
      custom.type = "button";
      custom.addEventListener("click", function () {
        send("vellum:home:time:custom");
      });
      buttons.appendChild(custom);
      block.appendChild(buttons);
      root.appendChild(block);
    }

    if (payload.showStudyBuilder) {
      const block = node("section", "vellum-home__card");
      block.appendChild(node("div", "vellum-home__eyebrow", "BUILD BY TOPIC OR TAG"));
      block.appendChild(node("h3", "", "Study Builder"));
      block.appendChild(
        node("p", "vellum-home__muted", "Inspect exact matches before creating a temporary scheduled-study deck.")
      );
      const button = node("button", "vellum-home__action", "Build Study Deck →");
      button.type = "button";
      button.addEventListener("click", function () { send("vellum:home:builder"); });
      block.appendChild(button);
      root.appendChild(block);
    }

    if (payload.showAttention && payload.attention.length) {
      const block = node("section", "vellum-home__card");
      block.appendChild(node("div", "vellum-home__eyebrow", "NEEDS ATTENTION"));
      payload.attention.forEach(function (item) {
        const row = node("div", "vellum-home__attention");
        row.title = item.reason || "";
        row.appendChild(node("span", "", item.label));
        row.appendChild(node("strong", "", item.state));
        block.appendChild(row);
      });
      root.appendChild(block);
    }
  }

  function updateEncoded(encoded) {
    try {
      const bytes = Uint8Array.from(atob(encoded), function (char) {
        return char.charCodeAt(0);
      });
      render(JSON.parse(new TextDecoder().decode(bytes)));
    } catch (error) {
      console.warn("Vellum Home payload rejected", error);
    }
  }

  window.VellumHome = {
    updateEncoded: updateEncoded,
    remove: function () {
      const root = document.getElementById("vellum-home");
      if (root) root.remove();
    },
  };
})();

(function () {
  "use strict";
  if (window.VellumHUD) return;
  let payload = null;
  let timer = null;

  function formatDuration(seconds) {
    const safe = Math.max(0, Math.floor(seconds || 0));
    const minutes = Math.floor(safe / 60);
    const remainder = safe % 60;
    return minutes + ":" + String(remainder).padStart(2, "0");
  }

  function ensureRoot() {
    let root = document.getElementById("vellum-hud");
    if (root) return root;
    root = document.createElement("aside");
    root.id = "vellum-hud";
    root.className = "vellum-hud";
    root.setAttribute("aria-label", "Vellum session status");
    root.setAttribute("aria-live", "polite");
    document.body.appendChild(root);
    return root;
  }

  function render() {
    if (!payload) return;
    const root = ensureRoot();
    root.dataset.placement = payload.placement;
    root.dataset.theme = payload.theme || "auto";
    root.classList.toggle("vellum-reduced-motion", Boolean(payload.reducedMotion));
    root.hidden = payload.placement === "hidden";
    if (root.hidden) return;
    const elapsed = Math.max(
      payload.elapsedSeconds || 0,
      Math.floor(Date.now() / 1000) - payload.startedAt
    );
    const remaining =
      payload.targetSeconds == null ? null : Math.max(0, payload.targetSeconds - elapsed);
    const parts = [];
    if (payload.showCompleted) {
      const total = payload.showEstimatedTotal && payload.estimatedTotal != null
        ? " / ~" + payload.estimatedTotal
        : "";
      parts.push(payload.reviewed + total);
    }
    if (payload.showElapsed) parts.push(formatDuration(elapsed));
    if (payload.showRemainingTime && remaining != null) {
      parts.push("~" + Math.ceil(remaining / 60) + "m left");
    }
    const cardsPerMinute = elapsed > 0 ? payload.reviewed / (elapsed / 60) : 0;
    if (payload.showCardsPerMinute && cardsPerMinute > 0) {
      parts.push(cardsPerMinute.toFixed(1) + " cards/min");
    }
    if (
      payload.showEta &&
      payload.estimatedTotal != null &&
      payload.estimatedTotal > payload.reviewed &&
      cardsPerMinute > 0
    ) {
      const etaMinutes = Math.ceil(
        (payload.estimatedTotal - payload.reviewed) / cardsPerMinute
      );
      parts.push("~" + etaMinutes + "m ETA");
    }
    if (payload.showSessionTarget && payload.targetSeconds != null) {
      parts.push(formatDuration(payload.targetSeconds) + " target");
    }
    root.textContent = parts.join(" · ");

    const timeUp = payload.targetSeconds != null && remaining === 0;
    root.classList.toggle("is-time-up", timeUp && payload.endBehavior !== "no_stop");
    if (timeUp && payload.endBehavior === "soft_stop") {
      root.textContent = "Time’s up · finish this card";
    }
    if (payload.showProgressBar && payload.estimatedTotal) {
      root.style.setProperty(
        "--vellum-hud-progress",
        Math.min(100, (payload.reviewed / payload.estimatedTotal) * 100) + "%"
      );
      root.classList.add("has-progress");
    } else {
      root.classList.remove("has-progress");
    }
  }

  function updateEncoded(encoded) {
    try {
      const bytes = Uint8Array.from(atob(encoded), function (char) {
        return char.charCodeAt(0);
      });
      payload = JSON.parse(new TextDecoder().decode(bytes));
      if (timer) clearInterval(timer);
      render();
      timer = setInterval(render, 1000);
    } catch (error) {
      console.warn("Vellum HUD payload rejected", error);
    }
  }

  window.VellumHUD = {
    updateEncoded: updateEncoded,
    hide: function () {
      const root = document.getElementById("vellum-hud");
      if (root) root.hidden = true;
      if (timer) clearInterval(timer);
      timer = null;
    },
    remove: function () {
      const root = document.getElementById("vellum-hud");
      if (root) root.remove();
      if (timer) clearInterval(timer);
      timer = null;
      payload = null;
    },
  };
})();
