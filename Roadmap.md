# Developer Roadmap — Discord Question Exporter (Python)

> Goal: Build a reliable, accurate, offline Python script that reads historical messages from selected channels or an entire Discord server, extracts question messages (including Swedish keywords), deduplicates them using hash-based registry, and exports into a training-ready text file.

---

## 1. Overview & Goals

* **Accuracy:** Capture true user questions (support `?` and Swedish question patterns).
* **Reliability:** Stable on very large histories; resumable; checkpointed.
* **Performance:** Parallelize where safe but always respect Discord rate limits.
* **Safety & Security:** Never store bot token in repo; avoid personal data; persist only question text and non-sensitive metadata.
* **Deliverables:** `script.py`, `requirements.txt`, `config.json.example`, `dedupe_registry.json` (created on first run), `README.md`, tests, optional `build`/`exe` instructions.

---

## 2. Tech Stack & Libraries

* **Python 3.11+** (or 3.10+)
* **discord.py v2.x** (`pip install -U discord.py`) — official/compatible fork that supports `message_content` intent.
* **aiofiles** — async file writes (optional but recommended).
* **tqdm** — progress bars for CLI feedback (optional).
* **python-dotenv** — load token from `.env` (security convenience).
* **pytest** — unit tests (optional).
* **pyinstaller** — optional packaging to .exe (if requested).

`requirements.txt` example:

```
discord.py>=2.3
aiofiles
python-dotenv
tqdm
pytest
```

---

## 3. Project Structure

```
discord-question-exporter/
├─ script.py                # main CLI & orchestration
├─ exporter/
│  ├─ __init__.py
│  ├─ collector.py         # functions for reading channels & messages
│  ├─ detector.py          # question detection logic & Swedish keywords
│  ├─ dedupe.py            # hashing + registry management + checkpointing
│  ├─ storage.py           # safe file writes, atomic writes
│  └─ utils.py             # logging, backoff, helpers
├─ tests/
│  └─ test_detector.py
├─ config.json.example
├─ .env.example             # for BOT_TOKEN
├─ README.md
└─ requirements.txt
```

---

## 4. Config & Permissions

**config.json** (example):

```json
{
  "token_env": "DISCORD_BOT_TOKEN",
  "guild_ids": [],
  "channel_ids": [],
  "export_path": "export.txt",
  "dedupe_registry": "dedupe_registry.json",
  "checkpoint_file": "checkpoints.json",
  "language": "sv",
  "extra_keywords": ["fråga"]
}
```

**Bot permissions required** (on guild invite):

* `Read Messages/View Channels`
* `Read Message History`
* (optional) `Manage Messages` — NOT required

**Intents**: `message_content` must be enabled both in code and on the Discord Developer Portal.

---

## 5. Core Components (Detailed)

### 5.1 `collector.py` — Safe history traversal

Responsibilities:

* Accept a `discord.TextChannel` or list of channels.
* Use `async for msg in channel.history(limit=None, oldest_first=True)` to stream messages.
* Skip messages from bots (`msg.author.bot`).
* Honor checkpoints: if `checkpoints.json` contains `last_processed_message_id` for that channel, resume from next message.
* Write progress to `checkpoints.json` periodically (e.g., every N messages).

Concurrency

* Use an `asyncio.Semaphore(max_concurrent_channels)` (suggested default 3) to avoid firing many concurrent history queries.
* For very large servers, process channels sequentially by default; allow `--concurrency` override.

Rate limits & reliability

* Rely primarily on `discord.py` internal rate limit handling.
* Wrap history iteration in try/except for `discord.HTTPException`, `discord.Forbidden`, and `discord.InteractionLimit`.
* On transient errors, use exponential backoff (see `utils.backoff`).

### 5.2 `detector.py` — Question detection & Swedish support

Responsibilities:

* Simple tests:

  * `if "?" in content:` quick accept
* Regex / keyword rules (Swedish-aware):

  * Normalize text: `content = content.strip()` and `content = content.replace('\n',' ')`
  * Lowercase for keyword checks **but keep original for export**
* Swedish keywords (non-exhaustive):

  ```py
  SWEDISH_KEYWORDS = [
    "varför", "hur", "vad", "när", "vem", "vilken", "vilket", "vilka",
    "kan", "ska", "finns", "är", "gör", "var", "vart", "hurdan", "hur mycket"
  ]
  ```
* Patterns to avoid false positives: short fragments like `"?"` inside code blocks, embed links, or quotes. Use heuristics:

  * Ignore messages shorter than 3 characters.
  * If message inside triple-backticks (code block) and contains `?`, skip unless `--include-code`.
  * If message contains a URL and only `?` is part of URL query, ensure there's natural-language before/after.

Ranking / Confidence

* Assign a confidence score for each detected question (e.g., `{'source':'?', 'score':0.6}`) to allow downstream filtering.

### 5.3 `dedupe.py` — Hashing, registry, and checkpointing

Responsibilities:

* Compute SHA256 hash of a canonical representation of the question: e.g. `f"{channel.id}|{normalized_text}|{language}"`.
* Registry file format: JSON array or newline-delimited hashes. (JSON array preferred for simplicity.)
* On startup, load registry into a `set` in memory. If registry is too large, consider a Bloom filter + periodic persistence.
* On each new question:

  * If hash in registry: skip
  * Else: add to in-memory set and append to registry on disk

Durability & Performance

* Flush registry to disk periodically and at the end of processing.
* Use atomic file write (write to `.tmp` then rename) to avoid corrupting registry on crash.
* Optionally compress old registry backups.

Checkpointing

* Save last processed message ID per channel to `checkpoints.json` every N messages.
* On resume, collector starts after the saved message ID.

### 5.4 `storage.py` — Export & atomic writes

Responsibilities:

* Open `export.txt` in append mode with UTF-8 encoding.
* Use an async write mechanism (aiofiles) to avoid blocking the event loop.
* Export line format:

  ```
  [Channel Name] - [YYYY-MM-DD] Question text...
  ```
* Also write a `export_metadata.json` with counts, first/last processed timestamps, and script version.

---

## 6. Resilience & Rate Limit Strategy

Primary principle: **let the library handle low-level rate limits** but code defensively for high-level errors.

* `discord.py` has built-in RL handling for REST endpoints — use it.
* Avoid launching too many `channel.history` calls at once. Use semaphore to limit concurrency.
* On `discord.HTTPException` or 429, backoff with jitter: `sleep = base * (2 ** attempts) + random_up_to(base)`.
* Use a retry wrapper with max attempts (e.g., 5 attempts) for transient errors.
* For huge channels, consider chunked processing (paginate by message ID ranges) to make checkpoints more meaningful.

---

## 7. Logging & Observability

* Use Python `logging` with `RotatingFileHandler`.
* Log levels: DEBUG for dev, INFO for normal runs, WARNING/ERROR for failures.
* Key logs to include:

  * Channel processing start/finish
  * Number of messages scanned
  * Questions found / duplicates skipped
  * Checkpoint saves
  * Errors and retries

CLI should print an overall summary at the end (total scanned, total questions, duplicates skipped, exported lines).

---

## 8. Testing Strategy

* Unit tests for `detector.py` covering Swedish samples:

  * Typical: "Hur använder jag botten?" → detected
  * Edge cases: code-blocks, links, short messages, emoji-only.
* Integration test (manual): run against a small demo guild with controlled messages.
* Failure injection: simulate HTTPException and ensure retry/backoff works.

Example pytest case for Swedish:

```py
def test_swedish_keyword_detection():
    assert detect_question("Hur installerar jag detta?") is True
    assert detect_question("Låt oss testa: vad händer") is True
```

---

## 9. CLI / UX

`script.py` should offer:

* `--config config.json` (path)
* `--channels 123 456` override config
* `--all-channels` flag to scan every accessible channel
* `--concurrency N` (safeguard default 2 or 3)
* `--dry-run` (detect but don't write export)
* `--include-bots` (default False)
* `--keywords-file path` to add Swedish/custom keywords

Example run:

```bash
DISCORD_BOT_TOKEN=xxxx python script.py --config config.json --all-channels
```

---

## 10. Packaging & Distribution (Optional)

**Exe via PyInstaller (optional):**

* Add a small build step to create a single-folder distribution or one-file exe.
* Important: still recommended to keep config/token out of exe — use environment variables or external config file.
* Extra charge if client wants a ready-made `.exe` for Windows.

---

## 11. Deliverables Checklist

* [ ] `script.py` (main)
* [ ] `exporter/` module (collector, detector, dedupe, storage, utils)
* [ ] `requirements.txt`
* [ ] `config.json.example` & `.env.example`
* [ ] `README.md` with run & permission instructions
* [ ] `dedupe_registry.json` (created by first run)
* [ ] `checkpoints.json` (created by first run)
* [ ] Unit tests for detector
* [ ] Example `export.txt` from test run

---

## 12. README Sections to Include (for buyer delivery)

* Purpose & overview
* Prerequisites (Python version, Discord bot setup)
* How to create a bot, invite with required permissions
* How to configure `config.json` or env var
* How to run (examples for Windows/Linux/macOS)
* How deduplication works and how to reset it
* How to resume after crash
* How to add Swedish keywords
* Optional: how to build an exe

---

## 13. Security & Privacy Notes

* **Token handling:** Use environment variables or `.env` files; do not commit tokens to VCS.
* **Data minimization:** Only store question text + minimal metadata (channel name/id, date). Do not store user IDs or full message objects unless buyer explicitly requests it.
* **Privacy:** Add note in README to anonymize or redact PHI/PII before training if needed.

---
