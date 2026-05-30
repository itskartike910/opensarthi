# OpenSarthi — Python AI Runtime

This is the intelligence layer of OpenSarthi. It runs as a **headless sidecar process** spawned by the Tauri shell. Built with **FastAPI + PydanticAI**, it handles all AI orchestration, tool execution, voice processing, real-time WebSocket communication, and persistent storage.

---

## 🧠 Core Architecture

```
Tauri Shell  ──WebSocket──►  FastAPI / websocket.py
                                     │
              ┌──────────────────────┼────────────────────────────┐
              ▼                      ▼                            ▼
        AgentRuntime           voice/stt.py               config.py / db.py
              │                 (Dual STT)                (settings + SQLite)
    ┌─────────┴──────────┐
    ▼                    ▼
planner/agent.py     tools/
(PydanticAI)      desktop.py / system.py
    │
    ▼
LLM Provider (Gemini, GPT-4o, Claude, Groq, OpenRouter, Ollama)
```

### Startup & Port Negotiation

`main.py` binds to an OS-assigned free port and prints `PORT:<number>` to stdout. The Tauri Rust layer (`sidecar.rs`) reads this, stores the port, and the frontend WebSocket client connects automatically. This avoids hardcoded port conflicts.

---

## ✅ Feature Reference

### 1. Multi-Provider LLM with Skill-Aware Prompts

Providers are set in `config.py` (reads `~/.config/opensarthi/.env`):

| Provider | Default Model |
|----------|-------------|
| **Google** | `gemini-2.5-flash` |
| **OpenAI** | `gpt-4o` |
| **Anthropic** | `claude-opus-4-5` |
| **Groq** | `llama-3.3-70b-versatile` |
| **OpenRouter** | any via `openrouter.ai/api/v1` |
| **Ollama** | `qwen2.5-coder:3b` (local) |

The system prompt is built **dynamically at runtime** by `build_system_prompt()` in `planner/agent.py` based on user-selected skills:

- If `desktop_automation` skill is **not** selected → the JSON tool-call format is completely omitted from the prompt, saving significant tokens for pure chat users.
- Skill sections (developer, admin, media, writing, etc.) add targeted context hints.
- `user_name` and `custom_prompt` from settings are prepended to the base identity.

### 2. AgentRuntime — Stateful Execution Engine

`agent_runtime.py` is the core execution loop:

```
AgentRuntime.run(goal, model, history)
    │
    ├─ Take desktop snapshot (observation.py)
    ├─ build_structured_context() → assembles LLM prompt
    ├─ _agent_run() → asyncio.Task wrapping agent.run() [CANCELLABLE]
    ├─ Parse JSON plan from LLM response
    │
    └─ For each step in plan:
         ├─ _check_pause() → await if paused
         ├─ Emit tool_started via WebSocket
         ├─ _tool_execute() → asyncio.Task [CANCELLABLE]
         │     └─ tool.safe_execute(args, deps)
         ├─ Emit tool_completed / tool_error
         ├─ Update observer snapshot
         └─ On failure: replan (max 3 attempts)
```

**Stop/Cancel:** `request_cancel()` immediately calls `.cancel()` on both `_agent_task` and `_tool_task` — this interrupts LLM inference mid-stream as well as tool execution.

**Pause/Resume:** `pause()` clears the `asyncio.Event`; the loop blocks at `_check_pause()`. `resume()` sets the event.

**JSON Plan Direct Run:** `run_plan_directly(steps, goal)` bypasses LLM entirely — runs a pre-built step list immediately (used by JSON import feature in frontend).

### 3. Voice Pipeline

Two parallel STT systems:

| Engine | Model | Best For |
|--------|-------|---------|
| **Google SpeechRecognition** | Cloud | Fast, low-latency |
| **Whisper (faster-whisper)** | Local | Accurate, offline |

- **Wake Word:** OpenWakeWord listens passively for `"hey sarthi"` / custom phrases
- **VAD (Voice Activity Detection):** Silence-based end-of-speech detection
- **Echo Protection:** Suspends STT capture while TTS is speaking
- **TTS:** Kokoro neural TTS with configurable accent and speed

### 4. Conversation History & Token Tracking

`db.py` manages SQLite at `~/.config/opensarthi/opensarthi.db`:

| Table | Purpose |
|-------|---------|
| `messages` | Stores role/content/timestamp per thread_id |
| `threads` | Thread metadata |
| `thread_tokens` | Accumulated token usage per thread |

- **20-message sliding window** — only the last 20 messages are sent to the LLM
- **Token usage per thread** — stored and restored when opening history
- **`result.usage`** — PydanticAI ≥ 0.2 changed this from a method to a property

### 5. Personalization & Settings (`config.py`)

```python
class Settings(BaseSettings):
    ai_provider: str = "google"
    local_model: str = "qwen2.5-coder:3b"
    cloud_model: str = "gemini-2.5-flash"
    # API Keys
    gemini_api_key: str = ""
    openai_api_key: str = ""
    # ... other keys
    # Personalization
    user_name: str = ""
    user_skills: list[str] = []
    custom_prompt: str = ""
    # Voice
    voice_accent: str = "af_heart"
    voice_speed: float = 1.0
```

All settings are read from `~/.config/opensarthi/.env` via `pydantic-settings`. Empty key inputs retain the existing saved value (no accidental wipe). Settings sync is triggered by the `update_settings` WebSocket message.

---

## 📂 Directory Structure

```
runtime/
├── main.py               # FastAPI app, port negotiation, CORS
├── config.py             # pydantic-settings, save_settings_to_env()
├── db.py                 # SQLite: messages, threads, token tracking
├── agent_runtime.py      # Stateful executor (cancel/pause/run/plan)
├── observation.py        # DesktopObserver: screenshot + window info
├── state_machine.py      # AgentState enum + AgentStateContext
├── sync_primitives.py    # Async helpers
├── requirements.txt
│
├── api/
│   └── websocket.py      # All WS message handlers (user_message, cancel, etc.)
│
├── planner/
│   ├── agent.py          # PydanticAI Agent, build_system_prompt(), AgentDependencies
│   └── schemas.py        # Plan, PlanStep, ToolResult Pydantic models
│
├── tools/
│   ├── base.py           # BaseTool abstract class
│   ├── desktop.py        # click, type_text, open_app, screenshot, focus_window
│   ├── system.py         # ShellTool (bubblewrap sandboxed)
│   ├── wait_tools.py     # wait_for_window, wait_for_text
│   └── registry.py       # TOOL_REGISTRY dict
│
├── providers/
│   └── linux/            # LinuxDesktopProvider (xdotool/ydotool)
│
├── voice/
│   ├── stt.py            # Dual STT: Google SpeechRecognition + Whisper
│   └── pipeline.py       # Wake word (OpenWakeWord), VAD, TTS playback
│
├── memory/               # LanceDB vector store (planned)
├── observer/             # Screenshot + OCR (planned)
├── security/             # bubblewrap profiles (planned)
├── llm/                  # LLM provider abstraction wrappers (planned)
└── mcp/                  # Model Context Protocol stubs (planned)
```

---

## 🚀 Running Standalone (Dev)

```bash
cd runtime
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
# Output: PORT:38495  ← picked up by Tauri frontend
```

---

## ⚠️ Python Version

**Use Python 3.12 exactly.**

- `faster-whisper`, `kokoro`, `numpy`, `blis` require pre-compiled wheels
- Wheels exist for 3.10 / 3.11 / **3.12** only
- Python 3.13+ will fail to compile ML packages from source

---

## 🔮 Planned

- [ ] **Memory** — LanceDB semantic search for long-term context
- [ ] **Observer** — real-time screenshot + OCR for screen-aware reasoning
- [ ] **Security** — bubblewrap profile expansion, per-app rules
- [ ] **MCP** — expose tools as Model Context Protocol server
- [ ] **LLM Caching** — cache Ollama model weights at startup
