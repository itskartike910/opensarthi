# OpenSarthi — Python AI Runtime

This is the brain of OpenSarthi. It runs as a **headless sidecar process** spawned and managed by the Tauri desktop shell. Built with **FastAPI + PydanticAI**, it handles all AI orchestration, voice processing, tool execution, memory, and real-time WebSocket communication with the frontend.

---

## 🧠 Architecture

```
Tauri Shell  ──WebSocket──►  FastAPI (uvicorn)
                                    │
                         ┌──────────┼──────────────┐
                         ▼          ▼               ▼
                    planner/    voice/          tools/
                    agent.py  pipeline.py    desktop.py
                         │          │               │
                    PydanticAI  SpeechRec.    xdotool/ydotool
                    + Provider   + Whisper     + bubblewrap
```

### Port Negotiation

On startup, `main.py` binds to an OS-assigned free port and prints `PORT:<number>` to stdout. The Tauri Rust layer reads this line, stores the port, and the frontend WebSocket client connects automatically.

---

## ✅ Completed Features

### 1. Multi-Provider AI with Cascading Fallback

Providers configured in `config.py` via `~/.config/opensarthi/.env`:

| Provider | Models |
|----------|--------|
| **Groq** | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768` |
| **Google** | `gemini-2.5-flash`, `gemini-2.0-flash` |
| **OpenAI** | `gpt-4o`, `gpt-4o-mini` |
| **Anthropic** | `claude-opus-4-5`, `claude-sonnet-4-5` |
| **OpenRouter** | Any model via `openrouter.ai/api/v1` |
| **Ollama** | Local models (default: `qwen2.5-coder:3b`) |

**Fallback logic (`api/websocket.py`):**
1. Cloud model runs via `agent.run(model=active_model)`
2. If it raises (e.g., Groq `400 tool_use_failed`), a clean **no-tools fallback agent** runs against the local Ollama model
3. If Ollama also fails, a descriptive error is returned to the UI (not a silent crash)

### 2. Groq Tool Hallucination Fix

Llama 3 models on Groq hallucinate tool calls (e.g., `brave_search`) for conversational queries. The system prompt in `planner/agent.py` explicitly forbids this:

```python
# planner/agent.py
SYSTEM_PROMPT = """
...
CRITICAL: Only call tools that are explicitly registered and available to you.
NEVER call tools that are not in your registered tool list (e.g. do NOT call
brave_search, web_search, or any tool not explicitly provided).
...
"""
```

### 3. Context Management & Token Tracking

- **20-message sliding window** — `db.get_history()` returns all messages; only the last 20 are sent to the LLM
- **Token usage extraction** — `result.usage` (property, not `.usage()` method — PydanticAI ≥ 0.2 changed this)
- **Response payload** includes `usage.request_tokens`, `usage.response_tokens`, `usage.total_tokens`
- **Frontend HUD** shows live `TOKEN USAGE` and cumulative `SESSION TOTAL`

### 4. Conversation History (SQLite)

`db.py` manages a persistent SQLite database at `~/.config/opensarthi/opensarthi.db`:

| Function | Description |
|----------|-------------|
| `save_message()` | Persist user/assistant messages with UUID and timestamp |
| `get_history()` | Retrieve all messages for a thread |
| `clear_thread()` | Delete messages for "New Chat" |

On first run, any existing development `opensarthi.db` in the `runtime/` directory is automatically migrated to the config directory — no chat history lost.

### 5. Voice Pipeline (`voice/pipeline.py`)

- **SpeechRecognition** for microphone capture (Google STT backend)
- **Echo Protection** — suspends capture while `is_speaking = True` (TTS playing)
- **8-second Silence Timeout** — automatically suspends the listener after inactivity
- **No phrase time limit** — supports arbitrarily long voice prompts

### 6. Production-Safe Configuration

All user state lives outside the AppImage read-only mount:

| File | Location |
|------|----------|
| API keys & settings | `~/.config/opensarthi/.env` |
| Conversation database | `~/.config/opensarthi/opensarthi.db` |
| Python venv (AppImage) | `~/.config/opensarthi/.venv` |

`config.py` uses `pydantic-settings` with `env_file=~/.config/opensarthi/.env`. Saving a setting with an empty API key input retains the existing saved key (no accidental wipe).

---

## 📂 Directory Structure

```
runtime/
├── main.py               # FastAPI app, port negotiation, sidecar entry
├── config.py             # pydantic-settings: reads ~/.config/opensarthi/.env
├── db.py                 # SQLite conversation store (aiosqlite)
├── requirements.txt
│
├── api/
│   └── websocket.py      # WebSocket router, message handling, agent execution,
│                         # multi-provider setup, fallback logic, token tracking
│
├── planner/
│   └── agent.py          # PydanticAI Agent, system prompt, tool declarations
│
├── tools/
│   ├── desktop.py        # click, type_text, screenshot (X11/Wayland provider)
│   └── system.py         # execute_command (bubblewrap sandboxed)
│
├── providers/
│   └── linux/            # LinuxDesktopProvider (X11 xdotool / Wayland ydotool)
│
├── voice/
│   └── pipeline.py       # SpeechRecognition, echo protection, silence timeout
│
├── memory/               # LanceDB vector store (semantic memory)
├── observer/             # Screenshot + OCR (mss + pytesseract + opencv)
├── security/             # bubblewrap sandbox, permission manager
├── llm/                  # LLM provider abstraction wrappers
└── mcp/                  # Model Context Protocol server & client stubs
```

---

## 🚀 Running Standalone (Dev)

```bash
# From the runtime/ directory
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

python main.py
# Output: PORT:38495  (picked up by Tauri frontend)
```

---

## ⚠️ Python Version Requirements

**Use Python 3.12 exactly.**

- `faster-whisper`, `kokoro`, `numpy`, and `blis` require pre-compiled wheels
- These wheels exist for 3.10 / 3.11 / **3.12** only
- Python 3.13+ / 3.14 (alpha) will attempt to compile from C++ source — this fails on standard Linux

---

## 🔮 Roadmap

- [ ] **Barge-in interruption** — wake-word trigger during active TTS playback
- [ ] **Model weight preloading** — cache Ollama model in memory at startup
- [ ] **bubblewrap profile expansion** — per-app configurable sandbox rules
- [ ] **MCP server** — expose desktop tools over Model Context Protocol
- [ ] **Keyring integration** — migrate API keys from `.env` to `libsecret`
