# Vellum configuration

Use **Vellum → Settings…** for the structured settings window. It includes:

- independent module switches;
- one global keyboard-shortcut switch plus independent feature shortcuts;
- Context content, position, width, remembered/pinned/auto-collapse behavior,
  appearance, and shortcuts;
- Recovery hierarchy defaults, modes, inclusion rules, limits, and shortcut;
- Study Builder default limit/preset/order, conflict-checked shortcut, ephemeral
  snippet visibility, AnKing facet visibility, the New preset, one-time tutorial
  version, and independent module switch. Saved recipes retain the chosen
  workflow, exact topic tags, source decks, sibling avoidance, and due/new
  composition;
- Time Machine presets, adaptive timing, fallbacks, deck Overview entry, every
  HUD metric/placement, and end behavior;
- Resume checkpoints, inactivity, staleness, history retention, and Home blocks;
- Return Ramp launch behavior, number of suggestions, and any positive
  whole-day absence threshold;
- Backtrack shortcut and in-memory history depth;
- Mind Notes shortcut, topic resurfacing, per-topic display limit, local history,
  and an explicit local-data reset;
- Session Debrief completion-card, ordinary-history, and handoff controls;
- topic-root priority, ignored values, renames, source-badge mappings, maximum
  depth, and live-card parser preview;
- cache/session/timing resets, Mind Note redaction from stored Debrief snapshots,
  and redacted diagnostics export;
- direct access to the offline Commands & Help center.

The JSON editor remains available as an advanced fallback. Vellum validates
values before use. Reset actions affect only Vellum's separate SQLite database;
**Reset all** always requires confirmation.

Default portable shortcuts are **C** for Context, **Shift+C** for Recovery,
**Ctrl+Shift+B** for Study Builder, **Alt+B** for Backtrack, and **Alt+M** for Mind Notes. Vellum stores portable Qt
sequences but displays `QKeySequence` NativeText: macOS may show symbols while
Windows shows native Alt/Ctrl labels.
Time Machine uses **Ctrl+Shift+T** because Anki 25.9.4 owns plain `T`; Vellum
still detects and disables any runtime conflict rather than overriding it.

Configuration schema version 3 adds Study Builder while continuing to track
onboarding content separately from the legacy completion boolean. Session
Debrief and Study Builder can be disabled independently and are unavailable
during the deliberate persistence fallback.
