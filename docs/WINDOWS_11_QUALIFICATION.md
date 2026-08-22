# Vellum Windows 11 qualification matrix

Last updated: 2026-08-22

## Current boundary

Vellum is **Windows-compatible in source, not yet live-qualified on Windows**.
Portable Qt shortcuts, native controls, system/Segoe UI font stacks, scrollable
dialogs, and light/dark offscreen renders are implementation evidence only. No
Windows result may be marked Pass until it is observed in a real Windows 11
Anki installation and recorded here.

## Test environment record

| Field | Required evidence | Status |
|---|---|---|
| Windows | Windows 11 edition, version, OS build | Pending |
| Anki | 25.9.4-compatible desktop build and architecture | Pending |
| Display | Resolution, monitor count, HDR state | Pending |
| Input | Keyboard layout and accessibility text settings | Pending |
| Add-ons | Stock pass, then representative conflict/coexistence pass | Pending |
| Candidate | `.ankiaddon` SHA-256 and Vellum version | Pending |

## Installation, restart, and storage

| Test | Acceptance | 100% | 150% | 200% |
|---|---|---:|---:|---:|
| Install from file | Candidate installs through Anki Add-ons without manual file edits | Pending | N/A | N/A |
| First profile open | Guided setup v2 opens once, remains responsive, and writes only on Finish | Pending | Pending | Pending |
| Set Up Later | Defaults remain unchanged and automatic prompting does not recur | Pending | Pending | Pending |
| Existing-user upgrade | One Deck Browser invitation appears; Start Tour and Not Now persist | Pending | Pending | Pending |
| Restart | Enabled modules, onboarding state, completion card, and handoff survive profile/app restart | Pending | Pending | Pending |
| Storage path | `user_files/vellum.sqlite3` and logs remain inside the installed add-on; no collection schema change | Pending | N/A | N/A |
| Upgrade preservation | Existing schema-6 sessions and generated histories survive schema 7 migration | Pending | N/A | N/A |
| Uninstall/reinstall | Document whether Anki preserves or removes `user_files`; no data outside the add-on path | Pending | N/A | N/A |

## Layout, themes, and keyboard navigation

Run every row in light and dark themes, at normal and increased Windows text
size where available.

| Surface | Acceptance | 100% | 150% | 200% |
|---|---|---:|---:|---:|
| Onboarding steps 1–5 | No clipping; scroll works; Back/Continue/Set Up Later and Ready actions are reachable | Pending | Pending | Pending |
| Commands & Help | Navigation list, document pane, tables, and Settings action are keyboard reachable | Pending | Pending | Pending |
| Completion and invitation cards | Copy wraps; buttons remain visible; focus indicators are clear | Pending | Pending | Pending |
| Full Debrief | Headline, ratings, topics, clusters, notes, CTA, handoff, and disclosure scroll safely | Pending | Pending | Pending |
| Session History | Selection, Enter activation, Open Debrief, and Close work without a mouse | Pending | Pending | Pending |
| Settings | All tabs, module controls, Help, and Data actions fit or scroll | Pending | Pending | Pending |

## Commands and conflicts

| Test | Acceptance | Status |
|---|---|---|
| Native labels | Windows shows Qt-native Alt/Ctrl text; no macOS-only glyph appears | Pending |
| Reviewer activation | Context and Recovery report Awaiting Reviewer, then Active or Conflict after Reviewer opens | Pending |
| Global disable | Every Vellum shortcut reports Globally Disabled and stops dispatching | Pending |
| Module disable | Disabled module commands report Module Disabled and install no behavior | Pending |
| Feature disable | Per-command switch reports Disabled without affecting other commands | Pending |
| Conflict | Stock Anki and another add-on retain their command; Vellum reports the conflict and does not override it | Pending |
| Dialog keys | Recovery 1–4 select the documented modes with standard Windows focus behavior | Pending |

## Primary workflow matrix

| Workflow | Required proof | Status |
|---|---|---|
| Normal study | Answer events enter Session History without a completion card | Pending |
| Time Machine exhaustion | Exact owned filtered deck is inspected and removed before terminal persistence and Debrief card | Pending |
| Recovery exhaustion | Exact owned filtered deck is inspected and removed before terminal persistence and Debrief card | Pending |
| Explicit Finish | Remaining cards return safely; Debrief reports the count and offers no false resume | Pending |
| Interrupted session | Remains a Resume candidate and creates no Debrief | Pending |
| Open/Dismiss | Completion-card state survives Anki restart | Pending |
| Recovery CTA | Stored recoverable topic opens topic-directed Recovery without the original Reviewer card | Pending |
| Handoff | Save, replace, clear, Done, and restart behavior match the newest-active rule | Pending |
| Legacy history | Pre-schema-7 topic rows show the honest unavailable-summary state | Pending |
| Privacy | Diagnostics and archive contain no card text, private database, logs, cache, Mind Note text, or handoff text | Pending |

## Release rule

All mandatory cells must have dated evidence and the candidate hash. Simulated,
offscreen, macOS, unit-test, or source inspection results cannot be copied into
this matrix as Windows passes.
