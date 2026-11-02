# Token Saver

**Know your tokens before you send.** A complete, local-first Python workbench to analyze prompts, choose a platform and model, estimate API costs, compare models, and review edits that reduce input tokens.

Built with **FastAPI, tiktoken, SQLite, and a responsive HTML/CSS/JavaScript interface**. No Node build, cloud database, account, or AI API key is required for local analysis.

## Quick start

Requires **Python 3.11 or newer** and an internet connection for the initial dependency and tokenizer-vocabulary downloads.

**Windows:** double-click `start.bat`. It creates an isolated virtual environment, installs the project, warms the tokenizer cache, and starts the server. Open **http://127.0.0.1:8000**. Close the terminal or press Ctrl+C to stop it.

**macOS / Linux:** run `sh start.sh`, then open the same URL.

After initial setup, you can start it with **`python app.py`**. This launcher
automatically uses the project's `.venv`; you do not need to activate it manually
or reinstall dependencies each time. Keep the terminal open; Ctrl+C stops it.

For manual setup from this directory:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m token_saver warmup
.venv\Scripts\python.exe -m token_saver serve
```

On macOS/Linux replace `.venv\Scripts\python.exe` with `.venv/bin/python`.

Once installed and cached, run `python -m token_saver serve` using your virtual environment for offline local analysis. The convenience launchers check installation each time, so use the direct command when offline.

## AI prompt optimizer (Groq)

1. Create a key at [Groq Console](https://console.groq.com/keys).
2. Copy `.env.example` to `.env` in this project folder, or edit an existing `.env` without overwriting its settings. Set `GROQ_API_KEY=your_key_here` and restart the server. Never put a real key in source code, a prompt or chat.
3. Enter your prompt and target model in **Prompt analyzer**, then open **AI optimizer**.
4. Choose **GPT OSS 120B** (default) or **GPT OSS 20B** (lower cost). Optionally paste exact text to protect, one snippet per line.
5. Click **Optimize prompt**. Review the rewrite, requirement checklist, token counts and cost. Click **Use rewrite & analyze locally** only when satisfied. **Undo AI rewrite** restores the original while it remains the current rewrite.

The optimizer sends only the prompt and protected snippets to Groq. System instructions, history, target settings and API keys are not included in the source prompt sent for editing. Keys are passed only as authentication to Groq. No tools or browsing are enabled. The rule-based healer and ordinary local analysis still work without a key.

The editor is instructed to preserve task, facts, language, format, tone, examples, conditions and negations. The server rejects rewrites that lose/change detected code blocks, quoted content, URLs, numbers or user-protected snippets, or that do not lower the selected target tokenizer's count. These are limited literal checks, **not proof of semantic equivalence**. The requirement checklist is AI-generated, not independent verification. Review instructions and test important prompts against your target model. Identical answers, answer quality and reduced output tokens cannot be guaranteed.

Savings use the **target model's** tokenizer, independently of the Groq editor. Claude/Gemini/Groq counts remain approximate. The report includes Groq's actual reported token usage, an estimated editor cost, input savings per target call, break-even uses and net savings for your configured call volume. It assumes one rewrite reused across those calls, uncached target input and unchanged output usage. One-off optimization can cost more than it saves. Missing usage is shown as unknown, never free. Failed or timed-out calls may also consume tokens; no automatic retries are made.

Limits: 20,000 prompt characters, 2,000 protected-text characters (40 snippets), one concurrent rewrite and 8,192 maximum completion tokens, including the structured response/reasoning budget. Incomplete or malformed responses leave the original unchanged. Proposals are kept only in the browser until you export a rewrite report or apply/save an analysis.

API: `GET /api/optimizer` exposes setup status and supported editors, never the key. `POST /api/optimize` accepts:

```json
{"request":{"prompt":"Please explain photosynthesis in order to help a beginner.","model_id":"gpt-5.4-mini"},"optimizer_model":"openai/gpt-oss-120b","keep_exact":""}
```

Groq rates checked November 2, 2026 (USD per million tokens): [GPT OSS 120B](https://console.groq.com/docs/model/openai/gpt-oss-120b) $0.15 input / $0.60 output; [GPT OSS 20B](https://console.groq.com/docs/model/openai/gpt-oss-20b) $0.075 input / $0.30 output. Both support [strict structured outputs](https://console.groq.com/docs/structured-outputs). Rates and account limits may change. Update `token_saver/optimizer.py` when needed.

## Included workflows

- Separate **platform/provider and model selectors**: OpenAI, Anthropic, Google Gemini, Groq, and Custom / other platform.
- Nine sourced presets; editable model catalog with rates, context/output limits, availability notes, and a verification date.
- Prompt, optional system instruction, and role-aware JSON conversation history.
- UTF-8 text-file import, character/word counts, a keyboard shortcut, and an example prompt.
- Exact text tokenization for the bundled OpenAI encodings; a clearly labeled rough heuristic for other providers.
- Optional Anthropic/Gemini token-count APIs, explicitly selected per analysis. No completion is generated.
- Low, expected, and high response budgets; separate reasoning, extra input and cached-input allowances.
- Per-call cost, volume cost, budget capacity, and context/output-limit checks.
- Side-by-side model cost comparison, JSON analysis export, and CSV comparison export.
- Token ID visualization, including honest UTF-8 byte-fragment handling.
- **Word-by-word token counts** in the original prompt, token pieces and IDs,
  searchable words, a 2+ token filter, and pagination through all words.
- Deterministic prompt-healing preview, optional shorter phrases, copy, and apply/recalculate.
- Explicit local saves, searchable and paginated SQLite history, restore/recalculate, and individual deletion.
- REST API with interactive documentation at `/docs`, Python CLI, tests, and a Docker setup.

## What the numbers mean

**Token Saver is a planning tool, not a billing oracle.** The same prompt can tokenize differently across models, and a platform can add hidden instructions, history or tools.

| Mode | What is measured | What remains approximate |
|---|---|---|
| Local OpenAI preset | Supplied text counted with `o200k_base` | Message formatting, hidden context, future output and reasoning |
| Local Claude/Gemini/Groq | Generic Unicode heuristic | All input counts and future output; no claim of a model-specific tokenizer |
| Provider mode | Provider-reported input count for supplied messages/system instruction | Future output, hidden platform additions, final billed usage; breakdown remains local |
| Custom | User-selected encoding or heuristic and user-supplied rates | Correctness of the encoding/model match and rates |

Local message formatting uses a transparent **4 tokens per message + 3** allowance. It is not an official framing rule for every model/API. Exact text counts do not imply exact request counts.

The generic heuristic estimates ASCII characters / 4 plus non-ASCII UTF-8 bytes / 3. Its displayed ±35% input sensitivity is a **what-if band, not a statistical confidence interval**. Actual counts can lie outside it. Models without bundled tokenizers may show the same local estimate; the app does not invent model-specific differences. Use provider mode to obtain their actual input count.

Response length is chosen by the user. Nothing in this app predicts what an LLM will actually generate. Add reasoning allowance where appropriate; actual reasoning can vary widely. The high scenario is checked against the model limits. Google input and output limits are checked separately; combined-context presets include the high output budget.

Prices are **USD per million text tokens**, for standard direct API usage. They are not ChatGPT/Claude/Gemini subscription costs or remaining app quotas. Third-party hosting rates may differ; use Custom. Tool fees, images/audio/video, cache writes/storage, taxes, regional markups, subscription fees, and multi-step agent loops are excluded.

```text
cost = ((uncached input × input rate)
      + (cached input × cached rate)
      + ((visible output + reasoning) × output rate)) / 1,000,000
```

Cache hits must be entered explicitly and are not guaranteed. GPT-5.4 long-context multipliers are applied above its configured threshold. Gemini 3.8 Flash's announced 2027 rate change is scheduled in the catalog. Model availability and prices can change: review the linked sources and update `token_saver/models.json`. After 30 days the app displays a stale-pricing notice. It never silently scrapes or updates prices.

## Which word uses how many tokens?

Analyze a prompt, then open **Which words use more tokens?** Each row shows a
whitespace-separated word (including punctuation), the number of original prompt
tokens touching that word, and the token pieces. Amber counts identify words
using two or more tokens. Search for a word or filter to multi-token words.

For `Hello world!` using `o200k_base`, `Hello` uses 1 token and `world!` uses 2.
The leading space stays attached to the ` world` token. Words are **not** counted
in isolation: surrounding spaces and punctuation affect tokenization.

Rare tokens may cross word boundaries. Such shared tokens are marked and counted
in every row they touch. Whitespace-only tokens are reported separately, so row
counts need not add up to the prompt total. Unicode alignment uses UTF-8 byte
positions, including tokens that split an emoji or a character. Results paginate
in groups of 100 words; a very long word shows at most 64 pieces while retaining
its full count.

Word-level counts are available only when the selected tokenizer is bundled.
Claude/Gemini count endpoints return totals rather than token boundaries, so the
app explicitly reports word-level counts as unavailable for those providers.

## Optional provider counting

Copy `.env.example` to `.env` in the directory from which you start the server, then set only the keys you need:

```dotenv
ANTHROPIC_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
```

Choose a Claude or Gemini model, open **Advanced estimates**, and choose **Provider API**. Your supplied prompt, system instruction and history are sent to that provider's count endpoint. Local mode is always the default. Comparison stays local across all providers; reopening history also returns to local mode. Saving an analysis revalidates it on the server and repeats the count if provider mode is selected.

Keys stay server-side, are not returned to the browser or stored in the history database, and are never placed in URLs. Provider failures are reported explicitly; the app does not silently replace a failed provider count with a heuristic. Actual provider calls require valid credentials/model access. Automated tests mock these calls. Counting does not generate completions; the separate, explicitly invoked Groq optimizer does generate a rewrite.

## Command line

```powershell
python -m token_saver models
python -m token_saver analyze --text "Explain gravity in two sentences."
python -m token_saver analyze --file examples/prompt.txt --model claude-sonnet-5-5 --output 256 --calls 10000 --json
python -m token_saver serve --port 8080
```

The `token-saver` command is also installed by pip. CLI analysis uses local counting, does not save history, and accepts `--reasoning` for a reasoning budget.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/health` | Health and version |
| `GET /api/models` | Catalog and provider-key availability (booleans only) |
| `POST /api/analyze` | Analyze a request without saving |
| `POST /api/compare` | Compare locally across catalog models |
| `POST /api/heal` | Preview deterministic edits |
| `POST /api/words` | Word/token alignment, filtering and pagination |
| `POST /api/history` | Recalculate and explicitly save |
| `GET /api/history?q=&limit=20&offset=0` | Search/list saved analyses |
| `GET /api/history/{id}` | Read a saved request and result |
| `DELETE /api/history/{id}` | Delete a saved analysis |

See `examples/request.json` and interactive schemas at **http://127.0.0.1:8000/docs**. Example Python client:

```python
import httpx

result = httpx.post("http://127.0.0.1:8000/api/analyze", json={
    "prompt": "Explain recursion with an example.",
    "model_id": "gpt-5.4-mini",
    "output_low": 128,
    "output_expected": 256,
    "output_high": 512,
}).raise_for_status().json()
print(result["counting"]["input_tokens"])
print(result["scenarios"]["expected"]["total_usd"])
```

## Project structure

```text
token-saver/
  token_saver/
    app.py          # FastAPI endpoints and local-service safeguards
    analyzer.py     # Counting, scenarios, pricing and comparisons
    catalog.py      # Model catalog and scheduled price changes
    models.json     # Editable presets and official source URLs
    tokenizer.py    # tiktoken, generic heuristic and token preview
    providers.py    # Opt-in Anthropic / Gemini count adapters
    healer.py       # Deterministic editing and suggestions
    schemas.py      # Validated request models
    storage.py      # SQLite repository
    cli.py          # Command-line interface
    static/         # Responsive interface; no frontend build required
  tests/            # Analysis, Unicode, pricing, API, storage and adapter tests
  examples/
  run.py
  pyproject.toml
  start.bat / start.sh
  Dockerfile / compose.yaml
```

The modules are separated so a later idea—an LLM-based rewrite, another provider, browser extension, editor integration, or authenticated multi-user deployment—can build on the same analysis engine.

## Tests

```powershell
python -m pip install -e ".[dev]"
python -m token_saver warmup
python -m pytest -q
```

Tests cover Unicode and literal special-token strings, pricing/cache arithmetic, scheduled/long-context pricing, context limits, request validation, protected prompt formatting, provider payloads/failures, persistence, and cross-origin protection. Provider tests use HTTP mocks. The first tokenizer use downloads its vocabulary; `warmup` makes subsequent tests offline.

## Docker

```sh
docker compose up --build
```

Open http://127.0.0.1:8000. History is stored in the named Docker volume. `docker compose down` stops the service without removing that volume. The image warms tokenizer data at build time and runs as a non-root user. Docker configuration is included for deployment; build it in an environment with Docker installed.

## Privacy and deployment scope

This release is a **single-user local application**. It binds to `127.0.0.1` by default, restricts Host headers, and rejects cross-origin browser writes. There is no account system, tenant isolation, or public-service authentication. Add those before exposing the app publicly. Local JSON exports and saved analyses contain the supplied prompts; saved history is not encrypted.

History defaults to `data/token_saver.sqlite3` under the working directory. Override it with `TOKEN_SAVER_DB`. No analysis is saved automatically. The browser uses no tracking or third-party assets. Initial tokenizer vocabulary downloads contain no prompt text. For a remote deployment, server-local storage means storage on that server rather than on the visitor's computer.

Limits: 100,000 prompt characters, 50,000 system-instruction characters, 100 history messages of at most 20,000 characters each, and 200,000 combined characters. Preview shows the first 400 prompt tokens; counting covers the full text. TXT, Markdown, JSON, Python and CSV imports are treated strictly as text; files are never executed. Images and PDFs are not parsed.

## Verified references

Catalog checked **November 2, 2026**. Each preset also stores its own source link.

- [OpenAI model pricing](https://developers.openai.com/api/docs/pricing)
- [OpenAI tiktoken](https://github.com/openai/tiktoken)
- [Anthropic pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Anthropic count tokens API](https://platform.claude.com/docs/en/api/messages/count_tokens)
- [Google Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Google countTokens API](https://ai.google.dev/api/tokens)

## Troubleshooting

- **Port busy:** `python -m token_saver serve --port 8080`.
- **Tokenizer unavailable:** connect once and run `python -m token_saver warmup`. Set `TIKTOKEN_CACHE_DIR` to a writable directory if necessary.
- **Dependency download timeout:** rerun the launcher when the connection is stable. No application or model API key is required for pip downloads.
- **Provider count rejected:** check the environment key and model access, or return to local mode. Legacy and deprecated models are labeled in the selector.
- **Cache tokens exceed input:** lower the cached-input assumption; the app never clamps it silently.
- **Invalid host:** use localhost or add the intended hostname to `TOKEN_SAVER_ALLOWED_HOSTS`. Do not use a wildcard for a public deployment.

## Groq analysis and comparison

Choose **Groq** under Platform / provider, then GPT OSS 120B or GPT OSS 20B.
Both work in local analysis, model comparison, the rule-based healer, saves,
exports and as target models for the AI optimizer. No API key is required for
analysis/comparison. GROQ_API_KEY is only needed to request an AI rewrite.
Counts are generic local estimates, not the Groq tokenizer or API usage.
Exact per-word token pieces are unavailable for these presets.

Rates checked November 2, 2026, USD per million tokens:

| Groq model | Input | Output | Cached input | Context | Maximum output |
| --- | ---: | ---: | ---: | ---: | ---: |
| GPT OSS 120B | 0.15 | 0.60 | 0.075 | 131,072 | 65,536 |
| GPT OSS 20B | 0.075 | 0.30 | 0.0375 | 131,072 | 65,536 |

Sources: [120B](https://console.groq.com/docs/model/openai/gpt-oss-120b),
[20B](https://console.groq.com/docs/model/openai/gpt-oss-20b),
[cached input discount](https://console.groq.com/docs/prompt-caching).
The cache rates apply Groq's documented 50% discount; actual cache hits are
not guaranteed. Include reasoning tokens in your response budget when relevant.
Groq's Llama offerings currently list Contact Sales pricing; use Custom with
your contracted rates rather than assuming their historical public prices.
