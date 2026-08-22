# Development and release checks

Vellum supports Python 3.10+ at the source boundary and targets Anki 25.09.4 or
newer for the 1.0.0 release.

Run from the repository root:

```bash
python3 -m unittest discover -s tests -t .. -v
env PYTHONPYCACHEPREFIX=/tmp/vellum-pycache python3 -m compileall -q .
node --check ui/assets/vellum.js
python3 scripts/build_package.py
python3 scripts/release_check.py
```

The release check verifies version consistency, public-source privacy, archive
contents, deterministic rebuilding, and SHA-256 output. Tests and source checks
are necessary but do not substitute for real Anki/Qt workflow qualification.

Real Anki integration harnesses live under `scripts/` and operate only on
disposable collections/bases. Run them with Anki's bundled Python from outside
the repository so this repository's `anki/` adapter directory does not shadow
Anki's installed package.

The public release boundary is:

- macOS + Anki 25.9.4: locally qualified candidate workflows;
- Windows: source-compatible, real Windows 11 matrix pending;
- Linux: not live-qualified for 1.0.0.
