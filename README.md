# Vellum for Anki

**Anki remembers your cards. Vellum remembers your studying.**

Vellum is a local-first study-continuity add-on for Anki Desktop. It adds topic
context, intent-first study building, deliberate recovery, realistic time-boxing, interruption-safe sessions,
and learner-facing debriefs while leaving Anki and FSRS fully responsible for
scheduling.

Vellum has no account, telemetry, cloud backend, API keys, or external data
requests. It never copies card question or answer text.

## What Vellum adds

- **Context** — an optional Reviewer sidebar with topic hierarchy, counts,
  maturity, retention, failures, and source badges.
- **Recovery** — a transparent Quick, Standard, Full, or Custom topic repair
  session built through Anki's native filtered-deck workflow.
- **Study Builder** — a full-window, guided deck builder with two clear paths.
  **Find Topics** lets you choose several topics and then shows only decks that
  contain them. **Browse Collection** lets you select parent decks/subdecks and
  then exposes only the tag hierarchy actually present inside that scope.
  Parent decks and tags include descendants; choosing specific children removes
  a redundant parent. The last step is a calm, inspect-only availability preview
  followed by **Build & Study**. A one-time tutorial and contextual `?` help are
  built in. Topic typing and tag filtering use immutable local indexes and never
  launch collection searches. Ordering, activation, Browser handoff, sibling
  control, and reusable recipes remain available without exposing Anki query
  syntax. Open it from Anki's **Builder** top-bar item, the Vellum menu, Home,
  Overview, or shortcut.
- **Time Machine** — choose the time you have and the deck groups you want;
  Vellum estimates a bounded queue from local timing evidence and safe fallbacks.
- **Session HUD** — quiet progress, elapsed/remaining time, pace, target, and ETA
  controls while you review.
- **Resume and Return Ramp** — truthful continuation after an interruption and a
  calm re-entry after time away.
- **Backtrack** — read-only access to the previous card and topic without
  answering, undoing, or changing scheduling.
- **Mind Notes** — private, topic-linked notes that resurface when the topic
  returns.
- **Session Debrief** — cards, active time, rating distribution, topic clusters,
  Mind Note activity, a calm next action, and an optional handoff to your future
  self.
- **Commands & Help** — a fully offline guide with live native shortcut labels,
  scopes, enabled states, and conflict reporting.

Every module can be disabled independently. Topic Health is opt-in because it is
an explicit workflow heuristic, not a mastery score.

## Install

### From AnkiWeb

Install from [AnkiWeb](https://ankiweb.net/shared/info/226947964) with download
code **226947964**. In Anki, open **Tools → Add-ons → Get Add-ons…**, enter the
code, install, and restart Anki.

### From GitHub

1. Download `vellum-1.1.0.ankiaddon` from the latest GitHub release.
2. In Anki, open **Tools → Add-ons → Install from file…**.
3. Select the downloaded file, restart Anki, and complete Getting Started.

Vellum 1.1.0 targets Anki **25.09.4 or newer**. It is qualified on macOS with
Anki 25.9.4 and 26.5. The source is designed for native Qt behavior on Windows, but the
real Windows 11 matrix is still pending; source compatibility is not presented
as live Windows proof. See [Windows qualification](docs/WINDOWS_11_QUALIFICATION.md).

## First use

The five-step Getting Started guide explains privacy and scheduler boundaries,
lets you choose modules atomically, detects topic roots from the local tag index,
shows your computer's native shortcut labels, and provides real workflow entry
points. You can reopen it at any time from **Vellum → Getting Started…**.

Open **Vellum → Commands & Help…** for the complete offline guide. Open
**Vellum → Settings…** to customize modules, shortcuts, topic parsing, timing,
appearance, session behavior, data retention, and diagnostics.

## Privacy and scheduling safety

- Anki and FSRS remain authoritative; Vellum does not replace the scheduler.
- Runtime data lives in Vellum's separate SQLite database under the add-on's
  Anki-preserved `user_files/` directory.
- Stored session records contain identifiers, timing, ratings, topic metadata,
  and only text deliberately written as a Mind Note or handoff.
- Card question and answer text are never copied into Vellum storage.
- Study Builder snippets are ephemeral. Recipes and recent runs store workflow
  choices and exact user-selected tag/deck selectors only—not rendered card content, extracted
  fields, suggestion counts, or zero-result probes.
- Diagnostics redact card/note IDs, paths, tag names, Mind Note text, and handoff
  text.
- Generated temporary decks are removed only after Vellum verifies the exact
  deck identity and safely returns unanswered cards to Anki.

Read the full [privacy and data guide](docs/PRIVACY.md).

## Default commands

Vellum stores portable Qt key sequences and displays them using Qt NativeText.
That means macOS may show symbols while Windows shows native Alt/Ctrl labels.
Conflicts are reported and never silently override Anki or another add-on.

| Command | Portable default | Scope |
|---|---|---|
| Context | `C` | Reviewer |
| Recovery | `Shift+C` | Reviewer |
| Time Machine | `Ctrl+Shift+T` | Anywhere |
| Study Builder | `Ctrl+Shift+B` | Anywhere |
| Backtrack | `Alt+B` | Anywhere |
| Mind Note | `Alt+M` | Anywhere |
| Collapse Context | `Escape` | Reviewer panel |
| Recovery modes | `1`–`4` | Recovery dialog |

## Development

Vellum's core, topic, Recovery, session, and timing logic is importable without
Anki. Qt and WebView dependencies stay at the integration edge.

```bash
python3 -m unittest discover -s tests -t .. -v
env PYTHONPYCACHEPREFIX=/tmp/vellum-pycache python3 -m compileall -q .
node --check ui/assets/vellum.js
python3 scripts/study_builder_anki_smoke.py  # use Anki's bundled Python
python3 scripts/build_package.py
```

These checks prove source logic and archive structure. They do not prove live
Anki rendering, scheduler behavior, third-party add-on coexistence, or another
operating system. See [development and release checks](docs/DEVELOPMENT.md).

## Support

Before reporting a problem, check [Troubleshooting](docs/TROUBLESHOOTING.md) and
export a redacted diagnostic from **Vellum → Settings → Data**. Please do not
attach your collection, Vellum database, card content, Mind Notes, or handoffs.

Report bugs and request features in
[GitHub Issues](https://github.com/Fateh-Alam/vellum/issues).
