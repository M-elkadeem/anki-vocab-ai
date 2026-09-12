"""
Anki Vocab Adder
-----------------
Look up words via an AI provider (meaning + example sentence), generate
pronunciation audio, and push everything straight into your Anki deck via
AnkiConnect - fully automatic. Words already in the deck are detected and
skipped (no duplicates). Fix any wording afterward directly inside Anki.

SETUP (one time):
1. Anki must be open, with the AnkiConnect add-on installed (code: 2055492159)
2. pip install requests gTTS
3. Create api_key.txt next to this script with your API key (see PROVIDER below)
4. Run:  python anki_vocab_adder.py

Edit DECK_NAME / MODEL_NAME below if you want different settings.
"""

import os
import json
import time
import base64
import tempfile
import requests
import tkinter as tk
from tkinter import messagebox
from gtts import gTTS

# ---------- CONFIG ----------
DECK_NAME = "Lektion 3"
MODEL_NAME = "Basic"  # or "Basic (and reversed card)"
ANKI_CONNECT_URL = "http://localhost:8765"

# Which AI provider to use for word lookups. Change this one line to switch:
#   "gemini"  - Google Gemini (needs an AIza... key)
#   "openai"  - OpenAI (needs an sk-... key)
#   "claude"  - Anthropic Claude (needs an sk-ant-... key)
PROVIDER = "gemini"

MODEL_BY_PROVIDER = {
    "gemini": "gemini-flash-latest",   # alias - always points to Google's current fast model
    "openai": "gpt-4o-mini",
    "claude": "claude-haiku-4-5-20251001",
}

# API keys: checks an environment variable first (GEMINI_API_KEY / OPENAI_API_KEY /
# CLAUDE_API_KEY depending on PROVIDER), then falls back to a local api_key.txt
# file sitting next to this script. You can put ONE key, or MULTIPLE keys (one
# per line, for the SAME provider) - if a key runs out of quota, the script
# automatically tries the next one before giving up.
_ENV_VAR_BY_PROVIDER = {
    "gemini": "GEMINI_API_KEY",
    "openai": "OPENAI_API_KEY",
    "claude": "CLAUDE_API_KEY",
}

API_KEYS = []
_env_key = os.environ.get(_ENV_VAR_BY_PROVIDER.get(PROVIDER, ""))
if _env_key:
    API_KEYS.append(_env_key.strip())

_key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "api_key.txt")
if os.path.exists(_key_file):
    with open(_key_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and line not in API_KEYS:
                API_KEYS.append(line)
# -----------------------------

if not API_KEYS:
    raise RuntimeError(
        f"No API key found for provider '{PROVIDER}'. Either set the "
        f"{_ENV_VAR_BY_PROVIDER.get(PROVIDER, '...')} environment variable, "
        f"or create a file named api_key.txt next to this script containing "
        f"one key per line."
    )

_current_key_index = 0  # which key in API_KEYS we're currently using


def build_request(word):
    """Returns (url, headers, json_body) for the current PROVIDER."""
    prompt = (
        f"The word '{word}' is German. Give:\n"
        f"1. A concise English definition/meaning of the word.\n"
        f"2. One very simple example sentence in German, written for an A1 (beginner) "
        f"learner — short, common vocabulary, present tense if possible.\n"
        f"Respond ONLY with raw JSON, no markdown, no backticks, in this exact format: "
        f'{{"meaning": "...", "sentence": "..."}}'
    )
    key = API_KEYS[_current_key_index]
    model = MODEL_BY_PROVIDER[PROVIDER]

    if PROVIDER == "gemini":
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={key}"
        )
        headers = {}
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        return url, headers, body

    if PROVIDER == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {key}"}
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        return url, headers, body

    if PROVIDER == "claude":
        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        }
        body = {
            "model": model,
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        }
        return url, headers, body

    raise ValueError(f"Unknown PROVIDER: {PROVIDER}")


def parse_response(data):
    """Extracts the raw text reply from a provider's response JSON."""
    if PROVIDER == "gemini":
        return data["candidates"][0]["content"]["parts"][0]["text"]
    if PROVIDER == "openai":
        return data["choices"][0]["message"]["content"]
    if PROVIDER == "claude":
        return data["content"][0]["text"]
    raise ValueError(f"Unknown PROVIDER: {PROVIDER}")


def anki_request(action, **params):
    payload = {"action": action, "version": 6, "params": params}
    resp = requests.post(ANKI_CONNECT_URL, json=payload, timeout=10).json()
    if resp.get("error"):
        raise RuntimeError(f"AnkiConnect error: {resp['error']}")
    return resp.get("result")


def ensure_deck_exists(deck_name):
    decks = anki_request("deckNames")
    if deck_name not in decks:
        anki_request("createDeck", deck=deck_name)


def get_word_info(word, max_retries=4):
    global _current_key_index

    last_error = None
    keys_tried = 0
    while keys_tried <= len(API_KEYS):  # allows one full pass over every key
        for attempt in range(1, max_retries + 1):
            try:
                url, headers, body = build_request(word)
                resp = requests.post(url, json=body, headers=headers, timeout=30)
                if resp.status_code == 429:
                    last_error = requests.HTTPError(
                        f"429 Rate limited (attempt {attempt}/{max_retries}, "
                        f"key #{_current_key_index + 1}/{len(API_KEYS)})"
                    )
                    if attempt < max_retries:
                        time.sleep(15)  # short-term rate limit - worth waiting out
                        continue
                    # exhausted retries on this key - try the next key, if any
                    if _current_key_index < len(API_KEYS) - 1:
                        _current_key_index += 1
                        break  # break attempt loop, outer while will retry with new key
                    raise last_error
                if resp.status_code in (500, 502, 503, 504):
                    last_error = requests.HTTPError(
                        f"{resp.status_code} Server Error (attempt {attempt}/{max_retries})"
                    )
                    if attempt < max_retries:
                        time.sleep(min(3 * attempt, 10))  # 3s, 6s, 9s, capped at 10s
                        continue
                    raise last_error
                resp.raise_for_status()
                data = resp.json()
                text = parse_response(data).strip()
                text = text.replace("```json", "").replace("```", "").strip()
                parsed = json.loads(text)
                return parsed["meaning"], parsed["sentence"]
            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = e
                if attempt < max_retries:
                    time.sleep(min(3 * attempt, 10))
                    continue
                raise
        else:
            # attempt loop finished normally (no break) - real failure, not a key swap
            raise last_error
        keys_tried += 1
    raise last_error


def generate_pronunciation_audio(text_to_speak, cache_key):
    """
    Generates German audio for `text_to_speak` using gTTS, uploads it to
    Anki's media folder via AnkiConnect, and returns the Anki sound tag
    (e.g. "[sound:anki_vocab_ai_word.mp3]") to embed in a card field.
    `cache_key` is used to build a stable filename (so re-adding the same
    word/sentence doesn't create duplicate media files).
    Returns None if generation/upload fails (card still gets added without audio).
    """
    try:
        tts = gTTS(text=f"... {text_to_speak}", lang="de")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tts.save(tmp.name)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            audio_bytes = f.read()
        os.remove(tmp_path)

        safe_name = "".join(c for c in cache_key if c.isalnum())[:40]
        filename = f"anki_vocab_ai_{safe_name}.mp3"

        anki_request(
            "storeMediaFile",
            filename=filename,
            data=base64.b64encode(audio_bytes).decode("utf-8"),
        )
        return f"[sound:{filename}]"
    except Exception:
        return None  # non-fatal - card still gets added, just without audio


def add_card_to_anki(word, meaning, sentence):
    """Returns 'added', 'duplicate', or raises on a real error."""
    ensure_deck_exists(DECK_NAME)

    # Check for a duplicate first (matches on the plain word, before any audio
    # tag is added) so we don't waste time generating audio for skipped words.
    probe_note = {
        "deckName": DECK_NAME,
        "modelName": MODEL_NAME,
        "fields": {"Front": word, "Back": ""},
    }
    can_add = anki_request("canAddNotes", notes=[probe_note])
    if can_add and not can_add[0]:
        return "duplicate"

    speak_word = word.split("/")[0].strip()  # clean base form for gendered pairs
    word_sound = generate_pronunciation_audio(speak_word, cache_key=word)
    front_field = f"{word} {word_sound}" if word_sound else word

    sentence_sound = generate_pronunciation_audio(sentence, cache_key=sentence)
    sentence_html = f"<i>{sentence}</i>"
    if sentence_sound:
        sentence_html += f" {sentence_sound}"

    note = {
        "deckName": DECK_NAME,
        "modelName": MODEL_NAME,
        "fields": {
            "Front": front_field,
            "Back": f"{meaning}<br><br>{sentence_html}",
        },
        "tags": ["auto-gemini"],
        "options": {"allowDuplicate": False},
    }
    payload = {"action": "addNote", "version": 6, "params": {"note": note}}
    resp = requests.post(ANKI_CONNECT_URL, json=payload, timeout=10).json()
    error = resp.get("error")
    if error:
        if "duplicate" in error.lower():
            return "duplicate"
        raise RuntimeError(f"AnkiConnect error: {error}")
    return "added"


# ---------------- GUI ----------------
class VocabApp:
    def __init__(self, root):
        self.root = root
        root.title("Anki Vocab Adder")
        root.geometry("480x520")

        # --- Input stage: multiple words at once ---
        self.input_frame = tk.Frame(root)
        self.input_frame.pack(fill="both", expand=True, padx=12, pady=12)

        tk.Label(
            self.input_frame,
            text="Enter words (one per line, or comma-separated):",
            anchor="w",
        ).pack(fill="x")
        self.words_box = tk.Text(self.input_frame, height=10, wrap="word")
        self.words_box.pack(fill="both", expand=True, pady=(4, 8))
        self.words_box.focus()

        tk.Button(self.input_frame, text="Add all automatically", command=self.start_batch).pack()

        tk.Label(
            self.input_frame,
            text="Cards are added straight to Anki. Words already in the deck\n"
                 "are skipped automatically (no duplicates). You can always\n"
                 "fix a meaning/sentence later inside Anki itself.",
            fg="gray",
            justify="left",
        ).pack(pady=(8, 0))

        # --- Progress stage: automatic run with a live log ---
        self.progress_frame = tk.Frame(root)

        self.progress_label = tk.Label(self.progress_frame, text="", font=("Segoe UI", 10, "bold"))
        self.progress_label.pack(pady=(0, 6))

        self.log_box = tk.Text(self.progress_frame, height=18, wrap="word", state="disabled")
        self.log_box.pack(fill="both", expand=True)

        tk.Button(self.progress_frame, text="◀ Back to word list", command=self.back_to_input).pack(pady=(10, 0))

        self.retry_button = tk.Button(
            self.progress_frame, text="🔁 Retry failed words", command=self.retry_failed
        )
        # only shown when there are failures - packed in process_next() when needed

        # Queue state
        self.queue = []
        self.added_count = 0
        self.duplicate_count = 0
        self.failed_words = []  # list of (word, reason)
        self._looked_up_before = False

    def log(self, text, tag=None):
        self.log_box.config(state="normal")
        self.log_box.insert("end", text + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")
        self.root.update_idletasks()

    def start_batch(self):
        raw = self.words_box.get("1.0", "end").strip()
        if not raw:
            return
        words = [w.strip() for chunk in raw.split(",") for w in chunk.splitlines()]
        words = [w for w in words if w]
        if not words:
            return

        self.queue = words
        self.added_count = 0
        self.duplicate_count = 0
        self.failed_words = []
        self._looked_up_before = False
        self.retry_button.pack_forget()

        self.input_frame.pack_forget()
        self.progress_frame.pack(fill="both", expand=True, padx=12, pady=12)
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

        self.process_next()

    def process_next(self):
        if not self.queue:
            self.progress_label.config(text="Done ✅")
            self.log(
                f"\nFinished: {self.added_count} added, "
                f"{self.duplicate_count} already existed (skipped), "
                f"{len(self.failed_words)} failed."
            )
            if self.failed_words:
                self.log("\nWords that did NOT get added:")
                for word, reason in self.failed_words:
                    self.log(f"   • {word}  —  {reason}")
                self.retry_button.pack(pady=(6, 0))
            return

        word = self.queue.pop(0)
        remaining = len(self.queue)
        self.progress_label.config(text=f"Processing '{word}'  ({remaining} left after this)")
        self.root.update_idletasks()

        if self._looked_up_before:
            time.sleep(3)  # pace requests to avoid free-tier rate limits
        self._looked_up_before = True

        try:
            meaning, sentence = get_word_info(word)
        except Exception as e:
            self.failed_words.append((word, f"{PROVIDER} lookup failed: {e}"))
            self.log(f"❌ '{word}': {PROVIDER} lookup failed ({e})")
            self.root.after(50, self.process_next)
            return

        try:
            result = add_card_to_anki(word, meaning, sentence)
        except Exception as e:
            self.failed_words.append((word, f"Anki add failed: {e}"))
            self.log(f"❌ '{word}': failed to add to Anki ({e})")
            self.root.after(50, self.process_next)
            return

        if result == "duplicate":
            self.duplicate_count += 1
            self.log(f"⏭ '{word}': already in deck, skipped")
        else:
            self.added_count += 1
            self.log(f"✅ '{word}': {meaning}")

        self.root.after(50, self.process_next)

    def retry_failed(self):
        words_to_retry = [w for w, _ in self.failed_words]
        self.queue = words_to_retry
        self.failed_words = []
        self.retry_button.pack_forget()
        self.log(f"\n--- Retrying {len(words_to_retry)} failed word(s) ---\n")
        self.process_next()

    def back_to_input(self):
        self.progress_frame.pack_forget()
        self.retry_button.pack_forget()
        self.input_frame.pack(fill="both", expand=True, padx=12, pady=12)
        self.words_box.delete("1.0", "end")
        self.words_box.focus()


if __name__ == "__main__":
    root = tk.Tk()
    app = VocabApp(root)
    root.mainloop()