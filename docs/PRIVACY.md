# Privacy and local data

Vellum is local-only. It has no account, telemetry, cloud backend, API keys, or
external data requests.

## What Vellum stores

Vellum uses its own versioned SQLite database under the add-on's
Anki-preserved `user_files/` directory. Depending on enabled modules, it stores:

- card and note identifiers, deck identity, answer ratings, and timings needed
  for session continuity and generated-deck safety;
- captured topic labels, paths, and raw topic prefixes;
- generated-deck manifests and lifecycle evidence;
- collection-scoped Study Builder recipes and recent-run definitions containing
  only user-authored queries, facet selectors, state/order choices, limits, and
  timestamps;
- Mind Note text and handoff text deliberately written by the user;
- configuration through Anki's supported add-on configuration API.

## What Vellum does not store or send

- card question or answer text;
- note fields or media;
- Study Builder snippets, rendered card content, or extracted sort-field text;
- Study Builder search matches, aliases, preview-cache entries, or zero-result diagnostic probes;
- account credentials or API keys;
- telemetry, analytics, or remote crash reports;
- any data outside the local Anki add-on area.

Nothing is sent to the Vellum author or any third party.

## Diagnostics and deletion

The diagnostic export omits card text, note fields, collection paths, raw tag
names, Mind Note text, and handoff text, and redacts known card/note identifiers
from relevant log lines.

Settings can clear individual Vellum histories or reset all Vellum-owned data.
Reset All requires confirmation and never targets Anki-owned collection tables.
Clearing Mind Notes also removes their text from durable Debrief snapshots.
Study Builder recipes/recent runs have their own explicit reset and diagnostics
report only configuration switches—not recipe queries, deck names, or tags.
