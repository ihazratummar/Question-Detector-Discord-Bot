# Discord Question Exporter

A reliable, accurate, offline Python script that reads historical messages from selected channels or an entire Discord server, extracts question messages (including Swedish keywords), deduplicates them using a hash-based registry, and exports them into a training-ready text file.

## Features
- **Accurate Question Detection**: Uses a combination of question marks, strong keywords (e.g., "varför", "hur"), and heuristics to identify questions.
- **Swedish Support**: Built-in support for Swedish question words and grammar.
- **Deduplication**: Prevents duplicate questions using a SHA256 hash registry.
- **Resumable**: Uses checkpoints to resume processing if interrupted.
- **Rate Limit Handling**: Respects Discord's rate limits with exponential backoff.
- **Concurrent Processing**: Scans multiple channels in parallel for speed.

## Prerequisites
- Python 3.11+
- A Discord Bot Token with `Message Content Intent` enabled.

## Installation

1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the example config and env files:
   ```bash
   cp config.json.example config.json
   cp .env.example .env
   ```
4. Edit `.env` and add your `DISCORD_BOT_TOKEN`.
5. (Optional) Edit `config.json` to customize settings.

## Usage

Run the script using `python3`:

```bash
python3 script.py --all-channels
```

### Options
- `--config`: Path to config file (default: `config.json`)
- `--channels`: List of channel IDs to scan (overrides config).
- `--all-channels`: Scan all accessible text channels.
- `--concurrency`: Number of concurrent channels to scan (default: 3).

## Configuration

`config.json`:
```json
{
  "token_env": "DISCORD_BOT_TOKEN",
  "guild_ids": [],
  "channel_ids": [],
  "export_path": "export.txt",
  "dedupe_registry": "dedupe_registry.json",
  "checkpoint_file": "checkpoints.json",
  "language": "sv",
  "language": "sv",
  "extra_keywords": ["fråga"],
  "hf_api_key": "YOUR_HUGGINGFACE_API_KEY",
  "use_ai_detection": false
}
```

### AI Question Detection (Optional)
To improve accuracy, you can use the free Hugging Face Inference API.
1. Get a free API key from [Hugging Face](https://huggingface.co/settings/tokens).
2. Add it to `.env` as `HUGGINGFACE_API_KEY`.
3. Set `"use_ai_detection": true` in `config.json`.

## Output
- `export.txt`: Contains the exported questions in the format: `[Channel Name] - [YYYY-MM-DD] Question text...`
- `dedupe_registry.json`: Stores hashes of processed questions to prevent duplicates.
- `checkpoints.json`: Stores the last processed message ID for each channel.

## Security
- Never commit your `.env` file or `config.json` with real tokens.
- The script only exports the question text and basic metadata (channel name, date). User IDs are NOT exported.


# Question-Detector-Discord-Bot
