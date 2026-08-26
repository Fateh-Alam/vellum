# Troubleshooting

## A command is inactive or conflicted

Open **Vellum → Commands & Help…**. Vellum reports whether the command is active,
globally disabled, module-disabled, feature-disabled, conflicted, or waiting for
Reviewer activation. Change the portable sequence in Settings; Vellum does not
override an existing Anki/add-on action.

## No topic appears

Open **Settings → Topic Parsing**. Check detected roots, priority, ignored
segments, maximum depth, and the current-card preview. Detection reads the local
tag index, never card text.

## A generated session is waiting

Use **Resume Last Session** to continue an interrupted Study by Time or Recovery
deck, or **Finish Current Session** to return unanswered cards safely. An
explicitly finished session is terminal and is not presented as resumable.

## Vellum reports persistence fallback

Vellum deliberately disables persistence-dependent modules when its private
storage is unavailable. Context can continue without persistence. Check that the
installed add-on directory and `user_files/` are writable, then restart Anki.

## Reporting a problem

Export a redacted diagnostic from **Settings → Data** and attach it to a GitHub
issue with reproduction steps. Do not attach your collection, `vellum.sqlite3`,
raw logs, card content, Mind Notes, or handoffs.
