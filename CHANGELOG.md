# Token Saver changes

## 1.3.0

- Added Groq GPT OSS 20B and 120B to the provider selector, analysis, and model
  comparison, with documented standard and cached-input rates.
- Labelled Groq counts as approximate and disabled unsupported provider counting
  and word-level token boundaries for these presets.
- Refreshed all pages with brighter emerald/teal accents, larger text, stronger
  contrast, visible keyboard focus, and roomier layouts on smaller screens.

## 1.2.1

- Fixed package discovery and added a root `app.py` launcher for Windows setup.

## 1.2.0

- Added the opt-in Groq AI prompt optimizer, GPT OSS 120B/20B selection, server-side
  API key setup, strict JSON responses and explicit cloud disclosure.
- Added protected snippets, literal checks, target-model token savings, optimizer
  usage/cost, break-even, and net savings for reused prompts.
- Added review/apply, undo, copy and JSON report export; stale proposals cannot be
  applied. Unsupported, unfinished and non-saving proposals keep the original.
- Improved offline server errors and added mocked optimizer regression coverage.

## 1.1.0

- Renamed the website, Python package, CLI, configuration variables and docs to
  Token Saver (`token_saver`, `token-saver`, `TOKEN_SAVER_*`).
- Added a searchable word-by-word token table with token pieces/IDs, a multi-token
  filter, pagination, Unicode byte alignment and explicit shared-token handling.
- Added `/api/words`; analysis JSON includes the first page under `word_preview`.
- Protected single/curly quoted text, lowercase SQL and verbatim instructions
  from automatic prompt shortening.
- Prevented stale model comparisons and exports after input changes.
- Added example-based API checks and expanded the unit suite to 70 passing tests.

The previous 1.0 release was named Token Healer. Use the new launcher and imports
when upgrading. Existing SQLite schemas remain compatible; set `TOKEN_SAVER_DB`
to an existing database if you want to reuse it.
