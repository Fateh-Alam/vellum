# Contributing

Thanks for helping improve Vellum.

Before opening a pull request:

1. Keep Anki and FSRS authoritative; do not replace scheduling or modify Anki's
   collection schema.
2. Keep runtime data inside Vellum's separate `user_files` database.
3. Never persist card question/answer text or add telemetry/network behavior.
4. Keep modules independently toggleable and pure logic importable without
   `aqt`.
5. Use native Qt controls and `QKeySequence.NativeText`; do not hard-code
   platform shortcut glyphs or fixed secondary-text greys.
6. Add tests and run the commands in `docs/DEVELOPMENT.md`.

Bug reports should include the Anki/Vellum versions, operating system, exact
steps, expected behavior, actual behavior, and a redacted diagnostic. Never
upload a collection, private database, card content, Mind Notes, or handoffs.
