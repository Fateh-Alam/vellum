# AnkiWeb listing source

Public listing: https://ankiweb.net/shared/info/226947964

Visual walkthrough: https://fateh-alam.github.io/vellum/

Download code: **226947964**

## Title

Vellum - Guided Study Builder, Recovery, and Session Continuity

## Tags

study workflow productivity recovery sessions anking deck-builder topics tags fsrs medical

## Support page

https://github.com/Fateh-Alam/vellum/issues/new/choose

## Description

**Short version:** Vellum helps you find a specific set of cards, check the
result, and put them into a scheduled filtered deck. Anki and FSRS still handle
the actual studying.

**See the real interface and complete visual walkthrough:**
https://fateh-alam.github.io/vellum/

---

## Why I built it

I was spending too much time in Anki's Browser combining resource tags, systems,
parent decks, and subdecks. The cards were already there; getting the exact set I
wanted was the annoying part.

Here is the basic use case. You want to study:

> Renal from First Aid and Pathoma, but only from my AnKing deck.

Anki can already find those cards, but you usually need to open the Browser,
navigate a very large tag tree, remember which tags are parents, combine several
search terms correctly, inspect card states, and then configure a filtered deck.

Vellum turns that into:

> choose topics → choose source decks → inspect cards → Build & Study

Vellum handles that setup. It does not provide medical content, generate cards,
or create a second scheduler.

---

## The Study Builder has two routes

### Route 1: Find Topics

Use this when you know **what subject you want to study**.

1. Search only topic and tag names, such as `renal`, `cardiology`, `Pathoma`, or
   `high yield`.
2. Select one or several topics. Several topics are alternatives. Selecting
   Renal and Acid–Base means **Renal OR Acid–Base**.
3. Vellum shows only the parent decks and subdecks that actually contain matching
   cards.
4. Select one or several source decks. Several source decks are alternatives.
   Selecting AnKing and Medicine means **AnKing OR Medicine**.
5. Vellum combines the two parts:

   `(Renal OR Acid–Base) AND (AnKing OR Medicine)`

6. Inspect exact availability and a small card preview.
7. Choose a card limit and select **Build & Study**.

You never need to type the Anki query shown above. It is only written here to
make the behavior unambiguous.

### Route 2: Browse Collection

Use this when you know **which deck should supply the cards**.

1. Select a parent deck or exact subdeck from a deck tree.
2. Checking a parent includes its descendant subdecks. The disclosure arrow only
   opens the parent so you can inspect children; it does not select the parent.
3. Vellum calculates only the hierarchical tags actually used by cards inside
   that selected deck scope.
4. Browse those tags as a tree—for example Resources → First Aid → Renal.
5. Checking a parent tag includes its descendants. Selecting a more specific
   child removes a redundant selected ancestor.
6. Inspect exact card availability, set a limit, and build.

There is also an explicit **Study entire selected deck scope** action when you do
not want an additional tag filter.

---

## What do the availability counts mean?

Before building, Vellum separates the result into:

- **Ready:** cards that can enter this filtered deck now.
- **Suspended:** matching cards that remain excluded unless you deliberately
  enable and confirm unsuspension.
- **Buried:** visible in the count but not pulled into the filtered deck.
- **In another filtered deck:** visible in the count but left with that existing
  filtered deck.

The preview is inspect-only. Vellum does not use the preview as a card editor.

You can choose:

- Due + New, Due, New, or All cards;
- a required numeric limit, default 100;
- due first, relative overdueness, most lapses, oldest seen, added order, or
  random;
- optional one-card-per-note sibling avoidance;
- an optional new-card share for Due + New sessions;
- optional, separately confirmed inclusion of suspended cards.

Vellum re-evaluates the complete definition immediately before building. A stale
preview cannot silently choose a different manifest.

---

## Will this destroy or rewrite my cards?

Vellum is designed with a narrow collection-mutation boundary, exact temporary
deck ownership checks, and rollback. No software can truthfully promise that it
can never contain a bug, so you should still keep Anki's normal automatic
backups and occasional manual exports.

### What Vellum does

- Reads Anki's local deck, tag, note-type, card-state, and scheduling indexes.
- Creates a uniquely named temporary **native Anki filtered deck**.
- Uses rescheduling mode so your answers behave like normal scheduled study.
- Records an exact manifest of the Vellum-generated deck and the cards Anki
  actually placed inside it.
- Returns remaining cards home and removes only the exact Vellum-owned deck when
  the session is safely finished.
- Stores Vellum-owned settings and continuity data in a separate local SQLite
  database under the add-on's Anki-preserved `user_files` directory.

### What Vellum does not do

- It does not delete your notes or cards.
- It does not rewrite card fronts, backs, note fields, or media.
- It does not rename, merge, add, or remove your tags.
- It does not modify Anki's collection database schema.
- It does not replace FSRS, choose your answer rating, or calculate replacement
  scheduling intervals.
- It does not silently unbury cards.
- It does not take cards already owned by another filtered deck.
- It does not upload your collection or send telemetry.

### The one optional permanent collection action

Suspended cards remain excluded by default. If you explicitly enable
**Unsuspend and include**, Vellum shows the exact number, requests confirmation,
and unsuspends only the limited card IDs selected for that run. Those cards stay
active afterward.

If filtered-deck creation fails before study begins, Vellum removes only the
newly created identity-checked deck and re-suspends exactly the cards activated
for that failed attempt.

Natural completion or explicit **Finish** returns remaining cards home and
removes the exact Vellum-owned temporary deck. An interrupted non-empty session
remains resumable. Only one unfinished Vellum-generated session may exist at a
time; Vellum offers Resume, Finish, or Abandon instead of silently stacking
sessions.

---

## What happens to scheduling and FSRS?

Anki and FSRS remain authoritative.

Vellum uses a scheduled, rescheduling-enabled native filtered deck. When you
press Again, Hard, Good, or Easy, Anki processes that answer and updates normal
review history and scheduling. Vellum does not replace that calculation, invent
intervals, or modify FSRS settings.

This is not preview/cram mode.

---

## Why this is useful for AnKing V12

AnKing is mainly organized with hierarchical tags because one card can relate to
several systems, exams, and resources while living in only one deck.

Vellum detects the hierarchy installed in your collection instead of assuming
one fixed V12 snapshot. When locally present, it can expose human-facing facets
for:

- Step 1, Step 2, and Step 3;
- systems and subjects;
- First Aid, B&B, Pathoma, Sketchy, Bootcamp, Pixorize, and other resources;
- yield tiers;
- Step overlap/relevance;
- resource chapters and video paths.

Parent tags include descendants. Deterministically equivalent Step copies can be
collapsed into one readable row while every exact raw backing tag is preserved
for the Anki query and saved recipe. Maintenance/update/duplicate tags stay out
of the ordinary view but remain available under **All tags**.

Vellum is not AnKing-only. It also supports ordinary decks/subdecks, generic
hierarchical tags, flat tags, decks without tags, Basic, Cloze, Image Occlusion,
and custom note/card types.

---

## Other Vellum modules

Every module can be disabled independently.

- **Context:** an optional Reviewer sidebar showing the current topic hierarchy
  and local topic evidence.
- **Recovery:** builds a bounded Quick, Standard, Full, or Custom topic repair
  session through Anki's native filtered-deck flow.
- **Time Machine:** choose available minutes and deck groups; Vellum estimates a
  bounded queue using local timing evidence and conservative fallbacks.
- **Session HUD:** quiet cards/time/pace/ETA information during a Vellum session.
- **Resume:** truthfully continues an interrupted generated session.
- **Return Ramp:** after time away, shows the real backlog and suggests a smaller
  first session.
- **Backtrack:** opens the previous card/topic read-only without answering,
  undoing, or changing scheduling.
- **Mind Notes:** saves private topic-linked text you deliberately write and
  resurfaces it when the topic returns.
- **Session Debrief:** shows cards, active time, rating distribution, topic error
  clusters, Mind Note activity, and an optional handoff to your future self.
- **Commands & Help:** a complete offline guide with native shortcut labels,
  enabled states, scopes, and conflict reporting.

Topic Health is opt-in and explicitly labeled as a workflow heuristic, never a
mastery score.

---

## Privacy: what leaves your computer?

Nothing is sent to the Vellum author or any third party.

Vellum has:

- no account;
- no telemetry or analytics SDK;
- no cloud backend;
- no API keys;
- no external data requests;
- no remote crash reporter.

Vellum never stores card question/answer text, note fields, media, Study Builder
snippets, rendered card content, suggestion counts, or zero-result diagnostic
probes.

Depending on enabled modules, its separate local database may store identifiers,
timings, answer ratings, topic metadata, exact generated-deck manifests, selected
recipe tags/decks, and text you deliberately write in Mind Notes or handoffs.

Diagnostics redact card/note IDs, collection paths, raw tag names, Mind Note
text, and handoff text.

Full data guide:
https://github.com/Fateh-Alam/vellum/blob/main/docs/PRIVACY.md

---

## Installation and first use

1. In Anki Desktop, open **Tools → Add-ons → Get Add-ons…**.
2. Enter code **226947964**.
3. Install and restart Anki.
4. Read the five-step Getting Started guide. It explains privacy and scheduling
   boundaries before asking which optional modules to enable.
5. Open **Builder** from Anki's top bar, or use **Vellum → Build Study Deck…**.
6. Choose Find Topics or Browse Collection, inspect the final scope, and build.

Getting Started can be reopened from **Vellum → Getting Started…**. The complete
offline guide is available under **Vellum → Commands & Help…**.

AnkiWeb installations are offered updates through Anki's add-on update check. A
manually downloaded GitHub `.ankiaddon` file is not attached to the AnkiWeb
listing and must be updated manually.

---

## Compatibility and evidence

Vellum 1.1.0 targets Anki Desktop **25.09.4 or newer**.

The v1.1.0 local qualification run included 162 unit tests, compilation and
JavaScript checks, deterministic package integrity, a 50,000-tag performance
fixture, disposable Anki-core deck/scheduling/rollback tests, native light/dark
Qt visual smokes, and isolated real Anki 26.5 desktop startup checks on macOS.

It was qualified on macOS with Anki 25.9.4 and 26.5. Windows-compatible source
is present, but the real Windows 11 qualification matrix remains pending. Linux
is not live-qualified for v1.1.0. Compatibility with every third-party add-on is
not claimed.

Development and qualification boundary:
https://github.com/Fateh-Alam/vellum/blob/main/docs/DEVELOPMENT.md

Source and release downloads:
https://github.com/Fateh-Alam/vellum

Bug reports, collection-safety concerns, and feature requests:
https://github.com/Fateh-Alam/vellum/issues/new/choose

General feedback and questions:
https://github.com/Fateh-Alam/vellum/discussions

Private security or privacy reports:
https://github.com/Fateh-Alam/vellum/security/advisories/new

Vellum is not affiliated with Anki, AnkiHub, or AnKing.
