# Anki Vocab AI

Automated vocab card generator for Anki. Type in a batch of words, and it looks up a meaning + example sentence via an AI provider, then pushes the cards straight into your Anki deck — no manual typing, no duplicates, fully automatic.

Currently tuned for **German vocabulary** (A1 level): the meaning comes back in English, and the example sentence is a simple beginner-level German sentence.

## Features

- **Batch processing** — paste multiple words at once (one per line, or comma-separated), and it processes the whole list automatically
- **Duplicate detection** — words already in your deck are skipped automatically, no errors
- **Automatic retries** — handles transient server errors and rate limits with backoff, without stopping the batch
- **Multiple API keys with fallback** — list several keys in `api_key.txt` (one per line); if one runs out of quota, the script automatically tries the next
- **Multi-provider support** — works with Google Gemini, OpenAI, or Anthropic Claude. Switch providers by changing a single line in the script
- **Failed word tracking** — anything that couldn't be added is listed clearly at the end, with a one-click retry button
- **Pronunciation audio** — generates spoken audio for both the word and its example sentence (via free Google TTS) and embeds a playable speaker icon on the Front and Back of each card
- **Simple GUI** — no terminal interaction needed once set up; a small popup window handles everything

## Requirements

- [Anki](https://apps.ankiweb.net/) desktop, with the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on installed (code: `2055492159`)
- Python 3.10+
- An API key for **one** of the supported providers:
  - **Gemini** (recommended — has a genuinely usable free tier): [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
  - **OpenAI**: [platform.openai.com/api-keys](https://platform.openai.com/api-keys) (requires billing/credit — no free tier)
  - **Claude (Anthropic)**: [console.anthropic.com](https://console.anthropic.com/) (requires billing/credit — no free tier)

## Setup

1. Install the required Python packages:
   ```
   pip install requests gTTS
   ```

2. Make sure Anki is open, with AnkiConnect installed. Test it by visiting `http://localhost:8765` in a browser while Anki is running — it should show `{"apiVersion": "AnkiConnect v.6"}`.

3. Create a file named `api_key.txt` in the same folder as the script, and paste your API key inside (just the key, nothing else). You can list **multiple keys** (one per line) for automatic fallback if one runs out of quota:
   ```
   your_first_key_here
   your_second_key_here
   ```
   > ⚠️ All keys in this file must belong to the **same provider** you've set in the script (see below). Don't mix a Gemini key and an OpenAI key in the same file.

4. Open `anki_vocab_adder.py` and set which provider you want to use, near the top of the file:
   ```python
   PROVIDER = "gemini"   # or "openai", or "claude"
   ```

5. Run it:
   ```
   python anki_vocab_adder.py
   ```
   Or on Windows, just double-click `Launch Anki Vocab Adder.bat`.

## Switching providers

To switch providers later:
1. Change the `PROVIDER` line in the script to `"gemini"`, `"openai"`, or `"claude"`
2. Replace the key(s) in `api_key.txt` with a key matching that provider
3. Save and run — no other changes needed

Note: `OPENAI` and `CLAUDE` require an active billing setup on your account (a payment method with some credit) — they don't offer free API usage the way Gemini's free tier does.

## Configuration

A few settings near the top of the script you can customize:

| Setting | What it does |
|---|---|
| `DECK_NAME` | Which Anki deck cards get added to (auto-created if it doesn't exist) |
| `MODEL_NAME` | Anki note type — `"Basic"` or `"Basic (and reversed card)"` |
| `MODEL_BY_PROVIDER` | Which specific model to use per provider |

## Notes

- This tool assumes input words are **German**. To adapt it for another language, edit the prompt inside `build_request()`, and change `lang="de"` in `generate_pronunciation_audio()` to the target language code.
- Pronunciation audio uses [gTTS](https://pypi.org/project/gTTS/), which requires an internet connection but no API key. If audio generation fails for any reason, the card still gets added — just without sound.
- `api_key.txt` is excluded from version control via `.gitignore` — never commit your API key.
- Card wording can always be fixed afterward directly inside Anki's card editor.

## License

Personal project — use and adapt as you like.