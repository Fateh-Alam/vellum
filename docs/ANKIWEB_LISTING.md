# AnkiWeb listing source

Public listing: https://ankiweb.net/shared/info/226947964

Website with screenshots: https://fateh-alam.github.io/vellum/

Download code: **226947964**

## Title

Vellum - Study Builder, Recovery, Study by Time, and Session Tools

## Tags

study workflow productivity recovery sessions anking deck-builder topics tags fsrs medical

## Support page

https://github.com/Fateh-Alam/vellum/issues/new/choose

## Description

Vellum is an Anki Desktop add-on I made because building a useful filtered deck
from a large medical collection had become a chore.

The main feature is **Study Builder**. It lets you choose topics and then choose
which decks those cards should come from. You can also do the reverse: choose a
deck first, then browse only the tags that are actually used inside that deck.

Vellum also adds tools for recovering a weak topic, planning a study session by
time, resuming interrupted work, leaving private notes for yourself, and seeing
what happened after a session.

It does not contain medical cards. It does not write answers for you. It does not
replace Anki or FSRS.

Screenshots and a visual walkthrough:
https://fateh-alam.github.io/vellum/

---

## Study Builder

Here is the sort of request Study Builder is meant to handle:

> Give me Renal or Acid-Base cards from AnKing or my Medicine deck.

You could make that search manually in Anki's Browser. Vellum gives you a guided
way to make the same choice without remembering search syntax or digging through
the entire tag tree.

Open it from **Builder** in Anki's top bar, from the Vellum menu, from the Home
screen, or from a deck's Overview screen.

### Find Topics

Use this route when you already know the subject you want to study.

1. Search for a topic or tag path, such as `renal`, `cardiology`, `Pathoma`, or
   `high yield`.
2. Pick one or several topics. If you select Renal and Acid-Base, a card may
   match either one. It does not need both tags.
3. Vellum checks which decks actually contain matching cards.
4. Pick the parent decks or exact subdecks you want to use as sources.
5. Inspect the matching cards and availability counts.
6. Choose a card limit and press **Build & Study**.

So choosing Renal and Acid-Base from AnKing and Medicine means:

`(Renal OR Acid-Base) AND (AnKing OR Medicine)`

You do not type that query. It is shown here only to explain exactly what Vellum
does with your selections.

### Browse Collection

Use this route when you know which deck you want to study from, but you do not
want to search the collection's full tag list.

1. Pick a parent deck or an exact subdeck from the deck tree.
2. Vellum checks which tags are actually used by cards in that deck scope.
3. Browse those tags as a normal hierarchy, such as
   `Resources > First Aid > Renal`.
4. Pick one or several tags.
5. Inspect the cards, set the limit, and press **Build & Study**.

Checking a parent deck includes its subdecks. Opening the arrow beside it only
shows the children; it does not select anything. The tag tree works the same way.
If you choose a specific child, Vellum removes a redundant selected parent so the
scope remains easy to understand.

If you want the whole selected deck scope with no tag filter, use **Study entire
selected deck scope**. Vellum still applies your card-state choice and limit.

### Search speed

Typing in the topic search does not run a fresh collection-wide Anki query for
every letter. Vellum searches a local tag/topic index and performs collection
work only after the selection changes. Old background results are ignored if you
make another choice before they finish.

### What the preview tells you

The final preview separates matching cards into four useful groups:

- **Ready:** can enter the new filtered deck now.
- **Suspended:** match the scope, but remain excluded unless you explicitly
  choose to unsuspend them.
- **Buried:** counted, but not placed in the filtered deck.
- **In another filtered deck:** counted, but left in that existing filtered
  deck.

The card preview is for checking the result. It is not another version of Anki's
Browser and it does not offer bulk card editing.

### Choosing the cards

You can choose:

- **Due + New**, **Due**, **New**, or **All** cards;
- a required card limit, which defaults to 100;
- due first, relative overdueness, most lapses, oldest seen, added order, or
  random order;
- **Avoid sibling cards**, which takes at most one card from each note;
- a preferred new-card percentage for Due + New sessions;
- whether suspended cards should be unsuspended and included.

If one side of a due/new percentage is too small, Vellum fills the remaining
places from the other side instead of returning a half-empty deck. Sibling
avoidance is applied before the final card list is accepted.

Vellum checks the search, counts, ordering, limit, sibling rule, due/new split,
and suspension state again immediately before it builds the deck. It does not
blindly reuse an old preview.

### Saved study decks

You can save a setup as a named recipe. The recipe stores the topics, decks, and
options you selected. It does not keep cards permanently trapped inside a
filtered deck.

Every time you run a recipe, Vellum searches the collection again. Newly added,
deleted, moved, retagged, suspended, or unsuspended cards can therefore change
the result. If a saved deck or tag no longer exists, Vellum shows it as missing
instead of deleting the rule and accidentally broadening the search.

### AnKing V12 support

AnKing gets particular attention because it relies heavily on hierarchical tags.
Vellum reads the tag structure installed in your own collection. It does not
assume that every user has one frozen copy of the V12 hierarchy.

When those paths exist, Vellum can recognize Step containers, systems, subjects,
First Aid, B&B, Pathoma, Sketchy, Bootcamp, Pixorize, yield tags, Step overlap,
and resource chapter/video paths. Equivalent Step copies can appear as one
readable choice while Vellum keeps all of the exact backing tags needed for the
real Anki search.

Maintenance, update, and duplicate tags are hidden from the normal topic list so
they do not crowd the useful results. They remain available in **All tags**.

Study Builder is not limited to AnKing. It also works with normal decks and
subdecks, flat tags, hierarchical tags, decks without tags, Basic cards, Cloze
cards, Image Occlusion cards, and custom note types.

### How this differs from Anki's Browser and filtered decks

Anki already has a powerful search language, a Browser, Custom Study, and native
filtered decks. Study Builder uses those abilities; it does not replace them.
What it adds is a guided way to choose topic tags and source decks, a deck-scoped
tag tree, an availability check, saved rules, and safer temporary-deck cleanup.
If you already enjoy writing Anki searches by hand, you can keep doing that.
Vellum is for the cases where finding and combining the right paths is the slow
part.

---

## Context sidebar

Context is an optional panel beside the card you are reviewing. It reads the
card's hierarchical tags and shows where the card sits, for example:

`First Aid > Renal > Glomerular disease`

This is useful when a card makes little sense in isolation and you need to see
the surrounding subject. Depending on your settings, the panel can also show
local counts, maturity, retention/failure information, source labels, a Mind
Note, and a button to start Recovery for that topic.

Context does not use the question or answer text to guess a topic. Topic parsing
comes from decks, tags, and your configured parsing rules.

### How this differs from Anki

Anki already shows a card's deck and tags in the Browser and Card Info. Context
does not create new metadata. It keeps the useful part of that existing tag
hierarchy visible beside the card while you review, and can connect that topic
to Recovery or a private Mind Note without making you leave the Reviewer.

---

## Topic Recovery

Recovery starts from the current card. You choose which level of its topic path
needs work, then choose how broad the repair session should be:

- **Quick:** the weakest cards with the smallest intervention.
- **Standard:** weak cards plus useful starting cards.
- **Full:** a wider review of the topic.
- **Custom:** choose the inclusion rules yourself.

Vellum shows the proposed cards before it builds anything. If you continue, it
uses Anki's filtered-deck system and normal scheduling. Recovery is for the
moment when one failed card tells you the gap is larger than that one fact.

### How this differs from Anki

In Anki, you can open the Browser, find the current card's tags, decide how broad
the topic should be, write a search, and make a filtered deck yourself. Recovery
starts that process from the card in front of you. Its Quick, Standard, Full,
and Custom choices decide how wide the topic repair should be, then show the
proposed cards before using Anki's normal filtered-deck machinery.

---

## Study by Time

Study by Time is for days when the real limit is time.

Choose how many minutes you have and which deck groups are allowed. Vellum uses
answer-time history stored on your computer to estimate how many cards fit. If
there is not enough personal timing history yet, it uses conservative fallback
times instead of pretending it knows your pace.

The estimate is a planning aid, not a promise that every card will take the same
number of seconds. The resulting session is still an ordinary scheduled Anki
filtered deck.

### How this differs from Anki

Anki can show due counts, limit cards, and report time spent. Its timebox feature
can also notify you after a chosen period while you are studying. Study by Time
works before the session: you give it minutes and allowed deck groups, and it
estimates a card count from your local answer times. It then builds that limited
queue with Anki rather than creating a separate study system.

---

## Session HUD

The HUD appears while you study a Vellum session. It can show completed and
remaining cards, active and elapsed time, recent pace, the session target, and an
estimated time remaining.

It is only a display. It does not decide which answer button you should press and
does not alter intervals.

### How this differs from Anki

Anki already shows basic remaining counts and records answer time. The Vellum
HUD is specific to the session Vellum built. It adds that session's target,
active-time estimate, recent pace, and ETA in one small display. These numbers
are informational and do not change Anki's queue.

---

## Resume

Vellum records checkpoints while you study. If Anki closes, you stop early, or a
generated session is interrupted, Resume tells you what it found before you
continue.

If the original temporary deck still matches, Vellum can resume that exact
session. If the queue has changed because more cards became due, it says so and
offers the current context instead of claiming it can restore an identical old
queue. You can also abandon an old session deliberately.

### How this differs from Anki

Anki normally leaves an unfinished deck available, so you can simply study it
again. Resume adds an explanation around Vellum-generated sessions: what you had
completed, what was expected to remain, whether the original temporary deck is
still the same, and whether newly due cards have changed the situation. It does
not duplicate Anki's scheduling state.

---

## Return Ramp

Return Ramp can appear after a configurable number of days away. It counts the
cards currently available across your active deck groups and separates review,
learning, and new cards. It then offers smaller time-based starting sessions.

It does not change the backlog merely because you opened the window. Nothing is
built until you choose a session. If an unfinished Vellum deck is already
waiting, Return Ramp points you back to Resume or Finish first.

### How this differs from Anki

Anki already shows the backlog in its deck counts and lets you use Custom Study.
Return Ramp does not hide or reschedule that backlog. It notices that you have
been away, puts the current review/learning/new workload in one window, and
offers smaller Study by Time sessions as a starting point.

---

## Backtrack

Backtrack lets you look at the previous card and the previous topic context in a
separate read-only window. It is useful when you move on and immediately realize
you want to compare the last card with the current one.

Viewing the old card does not answer it again, undo anything, or change its
scheduling. Backtrack keeps only what it needs for the current Anki run rather
than building a permanent archive of card contents.

### How this differs from Anki

Anki's Undo command reverses the previous action, and the Browser can preview a
card if you go and find it. Backtrack does neither. It opens the previous card
and previous topic for reference while leaving the answer and scheduling history
alone.

---

## Mind Notes

A Mind Note is a short private note attached to a topic, not to a public deck or
shared card. You might write:

> Compare proximal and distal RTA next time renal physiology comes up.

The note can reappear when the same topic returns. There is also a Mind Notes
history where you can review, replace, or clear your notes. This is the one place
where Vellum stores prose because it is text you deliberately wrote for
yourself. It is stored locally and is not added to the Anki card.

### How this differs from Anki

You can already add a field to an Anki note, mark a card, or edit its text. Those
changes belong to the collection and may sync or affect a shared note. A Mind
Note is separate Vellum data tied to the parsed topic. It is meant for a private
reminder to yourself and does not edit the card template or note fields.

---

## Session Debrief and handoffs

After a session, Debrief can show:

- cards completed;
- active study time;
- Again, Hard, Good, and Easy counts;
- topic groups where Again and Hard answers appeared;
- Mind Notes created or seen during the session;
- pace information when there is enough valid timing data;
- an optional one-line handoff for your future self.

A handoff is simply something you want to remember when you return, such as
“review nephritic vs nephrotic before adding new renal cards.” The newest handoff
can stay on Vellum's Home panel until you mark it done, replace it, or clear it.

Debrief describes what happened in the session. It does not diagnose mastery,
predict an exam score, or grade your knowledge.

### How this differs from Anki Stats

Anki Stats is the proper place for collection-wide review history, retention,
forecasting, and detailed scheduler data. Debrief is much narrower. It explains
one study session in ordinary terms and can preserve a one-line reminder for the
next time you open Anki. It does not replace Anki Stats or reinterpret FSRS.

---

## Home panel

The optional Home panel adds Vellum controls to Anki's deck screen. Depending on
what you enable, it can show:

- an interrupted session that can be resumed;
- a shortcut to Study Builder;
- a Study by Time starting point;
- an estimated workload;
- topics marked by the optional Topic Health rule;
- your current handoff.

Each block can be turned on or off in Settings.

### How this differs from Anki's deck screen

Anki's deck screen already lists decks and their new, learning, and due counts.
Vellum leaves that list in place. Its Home panel adds shortcuts and continuity
information that Anki does not associate with a Vellum session, such as a saved
handoff or an unfinished generated deck.

---

## Topic Health

Topic Health is optional and off by default. It uses recent reviews, failures,
and due-card load to sort topics into simple study-attention states. It is meant
to answer “where might I need to look next?”

It is a rule-based study hint. It is not a mastery score, medical-knowledge
assessment, or prediction of future performance. You can reset its recent-topic
data from Settings.

### How this differs from Anki Stats

Anki Stats reports real review and scheduling data. Topic Health takes a small
set of that local evidence and applies a simple rule to suggest topics that may
deserve attention. It is deliberately less ambitious than a statistical model,
and you should use Anki's own statistics when you need the underlying numbers.

---

## Session and generated-deck history

Vellum keeps local records needed to explain and safely clean up the temporary
decks it created. A generated-deck record can include the planned card IDs,
original deck IDs, queue positions, answer ratings, answer times, and whether the
temporary deck was removed.

It does not copy the front or back of those cards into the history. Old sessions
that predate complete tracking are labelled as reconstructed rather than being
presented as complete.

### How this differs from Card Info and Anki's review history

Card Info explains the review history of one Anki card. Vellum's generated-deck
history explains one temporary session: which card IDs were placed in it, where
they came from, what was answered, and whether Vellum removed its deck. It exists
mainly for cleanup, recovery, and auditability, not as a replacement for the
revlog or Browser.

---

## Getting Started, help, shortcuts, and settings

The first-run guide explains the privacy and scheduling boundaries, lets you
choose which modules to enable, and helps Vellum find useful topic roots. You can
open it again from **Vellum > Getting Started**.

**Vellum > Commands & Help** is an offline guide to the features and available
commands. Shortcuts are checked against Anki and other add-ons. If a key is
already taken, Vellum disables its conflicting shortcut rather than silently
overriding the existing one.

Settings include module switches, topic-root preferences, ignored tag segments,
display renames, a parser preview for the current card, timing defaults, absence
thresholds, Home-panel choices, history limits, diagnostic export, and separate
controls for clearing Vellum data.

Vellum refuses to erase the session/deck records it still needs to clean up an
active temporary deck safely.

### How this differs from Anki's add-on manager

Anki's add-on manager installs, updates, enables, disables, and configures
add-ons. Vellum's own Settings only control Vellum features and data. Its help
page explains Vellum commands, and its shortcut check avoids taking a key that
Anki or another add-on already uses. You still use Anki's add-on manager to
install, remove, or update Vellum.

---

## What Vellum changes in your collection

For Study Builder, Recovery, and Study by Time, Vellum creates a uniquely named
native Anki filtered deck. It uses rescheduling mode, so answers made inside that
deck update review history and scheduling in the normal Anki/FSRS way.

Vellum records the exact deck identity and the cards Anki placed inside it. When
the session finishes, remaining cards return to their home decks and Vellum
removes only the temporary deck it owns. An interrupted non-empty deck stays
available for Resume.

Only one unfinished Vellum-generated session can exist at a time. If one is
already present, Vellum asks you to Resume, Finish, or Abandon it before making
another.

### Suspended cards

Suspended cards stay suspended by default.

Study Builder has an optional **Unsuspend and include** switch. If you turn it
on, Vellum shows the exact number of selected suspended cards and asks for
confirmation. It unsuspends only those selected card IDs. They remain active
after the session.

If deck creation fails before studying begins, Vellum removes only the newly
created deck and re-suspends exactly the cards activated by that failed attempt.

### What Vellum does not do

- It does not delete notes or cards.
- It does not rewrite card fronts, backs, fields, or media.
- It does not rename, merge, add, or remove tags.
- It does not change Anki's collection database structure.
- It does not change FSRS settings or invent review intervals.
- It does not silently unbury cards.
- It does not pull cards out of somebody else's filtered deck.
- It does not upload your collection.

No add-on can honestly promise that it will never have a bug. Keep Anki's normal
automatic backups enabled and make occasional manual exports of collections you
cannot afford to lose.

---

## Privacy

Vellum has no account, advertising, telemetry, analytics service, cloud server,
API key, or remote crash reporter. It does not make outside network requests.

It does not store card questions, card answers, note fields, media, Study Builder
snippets, rendered card content, suggestion counts, or zero-result test queries.

Depending on the modules you enable, its separate database can store card/note/
deck identifiers, timings, answer ratings, parsed topic information, generated-
deck manifests, saved recipe selectors, and text you deliberately enter as a
Mind Note or handoff.

The diagnostic export removes card and note IDs, private paths, raw tag names,
Mind Note text, and handoff text. Check a diagnostic yourself before posting it.

Full data guide:
https://github.com/Fateh-Alam/vellum/blob/main/docs/PRIVACY.md

---

## Installation

1. In Anki Desktop, open **Tools > Add-ons > Get Add-ons**.
2. Enter **226947964**.
3. Install the add-on and restart Anki.
4. Read the Getting Started guide.
5. Open **Builder** from Anki's top bar or choose
   **Vellum > Build Study Deck**.

AnkiWeb installations receive updates through Anki's normal add-on update
check. If you install a `.ankiaddon` file manually from GitHub, that copy is not
connected to the AnkiWeb listing and must be updated manually.

---

## Compatibility and testing

Vellum 1.1.1 targets Anki Desktop **25.09.4 or newer**.

The 1.1.1 release was tested on macOS with Anki 25.9.4 and 26.5. The source has
Windows support, but the full Windows 11 test list has not yet been completed.
Linux has not been tested live for this release. I do not claim compatibility
with every third-party add-on.

The release checks included 162 unit tests, Python and JavaScript checks, package
integrity checks, a 50,000-tag search test, temporary Anki collections for deck
creation/scheduling/rollback tests, light and dark Qt interface checks, and real
Anki 26.5 startup checks on macOS.

Testing details:
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
