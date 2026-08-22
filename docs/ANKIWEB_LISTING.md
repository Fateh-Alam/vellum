# AnkiWeb listing source

Public listing: https://ankiweb.net/shared/info/226947964
Download code: **226947964**

## Title

Vellum - Study Continuity, Time Machine, Recovery, and Debrief

## Summary

Vellum adds topic context, time-boxed sessions, interruption-safe Resume,
deliberate topic Recovery, Mind Notes, and learner-facing Session Debriefs while
leaving Anki and FSRS fully responsible for scheduling.

## Description

**Anki remembers your cards. Vellum remembers your studying.**

Vellum is a local-first continuity layer for Anki Desktop:

- Context shows the current topic hierarchy in Reviewer.
- Recovery builds a transparent temporary topic session through Anki's native
  filtered-deck flow.
- Time Machine creates a bounded session for the time and deck groups you choose.
- Resume and Return Ramp help you continue truthfully after interruption or time away.
- Backtrack revisits the previous card/topic read-only.
- Mind Notes save private topic-linked thoughts and resurface them later.
- Session Debrief explains cards, active time, ratings, topic error clusters,
  Mind Note activity, a calm next action, and an optional future-self handoff.
- Getting Started and Commands & Help provide native shortcut labels, conflict
  states, topic setup, privacy guidance, and offline instructions.

Every module is independently toggleable. Topic Health is opt-in and is labeled
as a workflow heuristic, never a mastery score.

**Privacy:** no account, telemetry, cloud backend, API keys, or external data
requests. Card question and answer text are never copied. Vellum data stays in a
separate local SQLite database under the add-on's `user_files` directory.

**Scheduling:** Anki and FSRS remain authoritative. Vellum does not replace the
scheduler or modify Anki's collection schema.

**Compatibility:** Vellum 1.0.0 targets Anki 25.09.4 or newer and is qualified on
macOS with Anki 25.9.4. Windows-compatible source is present, but the real
Windows 11 qualification matrix is still pending and is not claimed as passed.

Source, documentation, release downloads, and support:
https://github.com/Fateh-Alam/vellum
