# Changelog

All notable public changes to Vellum are recorded here.

## 1.1.1 — 2026-08-26

- Renamed the user-facing **Time Machine** feature to **Study by Time** so its
  purpose is clear. Existing settings, recipes, session origins, and stored
  history continue to use the compatible internal `time_machine` identifier.
- Added a detailed public walkthrough with real interface captures, a plain-
  language explanation of Study Builder, explicit collection-safety boundaries,
  installation help, and responsive media that preserves its full aspect ratio.
- Added guided public forms for bugs, collection-safety concerns, and feature
  requests, plus separate general-feedback and private security-reporting links.

## 1.1.0 — 2026-08-25

- Added an independently toggleable, full-window Study Builder with two guided
  workflows: choose topics and then their source decks, or choose parent
  decks/subdecks and browse only the tags actually present inside that scope.
- Added descendant-inclusive deck and tag trees with distinct selection and
  disclosure actions, redundant-ancestor replacement, scoped totals, hidden
  maintenance tags, explicit entire-deck builds, and exact home-deck attribution
  for cards temporarily occupying filtered decks.
- Added deterministic generic and AnKing topic search, equivalent Step-path
  collapsing, local-only aliases, dynamic recipes, recent runs, exact
  availability previews, ordering, limits, and Anki Browser handoff.
- Replaced the dense condition composer with a calm three-step workspace: one
  focused canvas, a restrained progress rail, natural-language scope, native
  light/dark styling, and an inspect-only card preview.
- Kept topic typing and tag filtering entirely inside immutable local indexes;
  selection changes issue at most one stale-safe background scope operation and
  previews are cached by definition and collection revision.
- Added a module-aware **Builder** item to Anki's native top navigation bar, a
  one-time two-workflow tutorial, persistent tutorial help, and contextual
  question-mark tooltips for unfamiliar actions.
- Added confirmed limited-card unsuspension, immediate pre-build re-evaluation,
  exact filtered-deck manifests, compensating pre-study rollback, Resume/Finish/
  Abandon blocking, and Study Builder Debrief/history integration.
- Added config schema 3, builder-definition version 3, lossless version-2 recipe
  compatibility, and SQLite schema 8. Preview snippets and field content
  remain ephemeral and never enter recipes, logs, diagnostics, or Debriefs.
- Added 50,000-tag performance coverage, disposable Anki-core scope/build tests,
  and native light/dark, narrow-window, large-text, tooltip, and tutorial Qt
  qualification harnesses.

## 1.0.0 — 2026-08-22

- Added independently toggleable Context, Recovery, Time Machine, Session HUD,
  Resume, Return Ramp, Backtrack, Mind Notes, Home Panel, Topic Health, and
  Session Debrief modules.
- Added durable, privacy-bounded generated-deck history and interruption-safe
  session checkpoints.
- Added learner-facing Debriefs with rating metrics, topic error clusters,
  Mind Note activity, suggested actions, and future-self handoffs.
- Added versioned five-step onboarding and a fully offline Commands & Help
  center with native shortcut labels and conflict states.
- Added schema-7 and config-v2 migration paths.
- Added exact generated-deck cleanup checks and startup repair after interrupted
  finalization.
- Added cross-platform Qt layouts, Segoe/system font stacks, large-text-safe
  scrolling, and theme-derived secondary text for light/dark contrast.
- Qualified the release candidate locally on macOS with Anki 25.9.4. Windows
  source compatibility is present; real Windows 11 qualification remains open.
