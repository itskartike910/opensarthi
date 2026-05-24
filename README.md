# OpenSarthi

> **An AI-native Desktop Operating Layer & Assistant for Linux**

OpenSarthi is an autonomous, voice-first AI desktop agent built for Linux. It acts as a generalized computer-use primitive — executing system-level tasks, controlling apps, interacting with the screen, sandboxing shell commands, and responding to natural voice input. It is not just a chatbot; it is a full agentic runtime integrated directly into your desktop.

---

## 🏗️ Architecture Overview

OpenSarthi is a monorepo with two tightly integrated layers:

```
┌─────────────────────────────────────────────────────────┐
│               Tauri v2 Desktop Shell                    │
│        React 19 + TypeScript + Vite 6 (WebView)        │
│  Themes • HUD • Voice Button • Settings • Chat Panel   │
└────────────────────────┬────────────────────────────────┘
                         │  WebSocket (localhost)
┌────────────────────────▼────────────────────────────────┐
│              Python Runtime Sidecar                     │
│          FastAPI + PydanticAI + uvicorn                 │
│  Agent • Planner • Tools • Voice • Memory • Providers  │
└─────────────────────────────────────────────────────────┘
```

| Layer | Technology |
|-------|-----------|
| **Desktop Shell** | Tauri v2, React 19, TypeScript, Vite 6 |
| **Rust Core** | sidecar.rs, tray.rs, ipc.rs (Tauri shell plugin) |
| **AI Runtime** | Python 3.12, FastAPI, PydanticAI ≥ 0.2 |
| **LLM Providers** | Groq, Google Gemini, OpenAI, Anthropic, OpenRouter, Ollama |
| **Voice Pipeline** | SpeechRecognition, OpenWakeWord, faster-whisper, Kokoro TTS |
| **Storage** | SQLite (aiosqlite) + LanceDB (vector memory) |
| **Packaging** | AppImage (Tauri bundle) + `uv` for portable Python management |

---

## ✅ What's Built & Working

### Desktop Shell (Frontend)
- **Cyberpunk HUD UI** — three-panel layout: Active Tasks (left), Chat (center), Live Plan & Activity (right)
- **5 Premium Themes** — Glass Red-Black, Forest Green-Black, Deep Purple-Black, Cyber Sky-White, Sakura Pink-White
- **Real-time Token Counter** — live `request_tokens / response_tokens / session_total` display in bottom-left HUD
- **Provider & Model Settings** — cascading flow: Provider → Model → API Key → Save
- **Scrollable Task & Plan Panels** — both side panels scroll independently
- **New Chat** — clears session context and resets token counter
- **Voice Button** — microphone toggle with animated waveform and state indicators

### AI Runtime (Backend Sidecar)
- **Multi-Provider Support** — Groq, OpenAI, Anthropic, Google Gemini, OpenRouter, Ollama (local)
- **Context-Aware Conversations** — SQLite-persisted message history with a 20-message sliding window
- **Groq Tool-Hallucination Fix** — system prompt explicitly forbids undeclared tool calls (eliminates `brave_search` 400 errors)
- **Cloud → Local Fallback** — if cloud model fails (tool validation error, rate limit), a clean no-tools Ollama agent takes over
- **Production-Safe Config** — settings at `~/.config/opensarthi/.env`, database at `~/.config/opensarthi/opensarthi.db`
- **Token Usage Extraction** — `result.usage` (property, not method) returned on every WebSocket response
- **Voice Pipeline** — SpeechRecognition + echo protection + 8-second silence timeout

### AppImage Distribution
- **Portable Bootstrap Script** — `opensarthi-runtime-x86_64-unknown-linux-gnu` auto-creates venv, validates packages
- **Bundled `uv` Binary** — embedded in AppImage resources; downloads Python 3.12 automatically if not present
- **LD_LIBRARY_PATH Isolation** — clears `LD_LIBRARY_PATH`, `LD_PRELOAD`, `PYTHONHOME` before spawning system Python
- **Stale Venv Detection** — validates `import uvicorn, fastapi, speech_recognition` before reusing cached venv
- **linuxdeploy GTK Plugin Fix** — mock_pkg_config auto-creates dummy gdk-pixbuf directories to prevent `cp` failures during AppImage bundling

---

## 📦 Building the AppImage

```bash
# From the repo root
PATH="$(pwd)/apps/desktop/src-tauri/mock_pkg_config:$PATH" \
NO_STRIP=true \
APPIMAGE_EXTRACT_AND_RUN=1 \
pnpm tauri build -b appimage
```

Output: `apps/desktop/src-tauri/target/release/bundle/appimage/OpenSarthi_0.1.0_amd64.AppImage`

> **Note:** The `mock_pkg_config` override is needed because the linuxdeploy GTK plugin uses `pkg-config --variable=gdk_pixbuf_binarydir` which otherwise returns incorrect paths on Arch Linux. The mock wrapper creates the required directories and falls through to the real `pkgconf` for all other queries.

---

## 🛠️ Development Setup

### Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Node.js | 20+ | via nvm or system |
| pnpm | 9+ | `npm i -g pnpm` |
| Rust / Cargo | stable | `rustup update stable` |
| Python | **3.12** | Required for ML wheels |

> ⚠️ **Python 3.14+ is NOT supported.** Pre-compiled wheels for `faster-whisper`, `kokoro`, and `numpy` are not available for alpha Python releases.

### Setup

```bash
# 1. Install JS dependencies
pnpm install

# 2. Set up the Python runtime venv (Python 3.12 required)
cd runtime
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd ..

# 3. Run in development mode
pnpm dev
```

---

## 📁 Repository Structure

```
opensarthi/
├── apps/
│   └── desktop/                     # Tauri v2 + React 19 frontend
│       ├── src/                     # React/TypeScript source
│       │   ├── App.tsx
│       │   ├── components/
│       │   │   ├── assistant/       # AssistantOverlay, TaskList
│       │   │   ├── execution/       # Execution plan panels
│       │   │   ├── permissions/     # Permission dialog
│       │   │   └── settings/        # SettingsView (provider → model → key)
│       │   ├── hooks/
│       │   │   └── useWebSocket.ts  # WebSocket client with reconnect
│       │   ├── stores/              # Zustand state stores
│       │   └── styles/              # Global CSS + theme tokens
│       └── src-tauri/
│           ├── src/
│           │   ├── lib.rs           # App entry, sidecar launch
│           │   ├── sidecar.rs       # Python process management
│           │   ├── tray.rs          # System tray
│           │   └── ipc.rs           # Tauri IPC commands
│           ├── binaries/
│           │   └── opensarthi-runtime-x86_64-unknown-linux-gnu  # Bootstrap script
│           ├── resources/
│           │   └── uv               # Bundled uv binary (portable Python manager)
│           ├── mock_pkg_config/
│           │   └── pkgconf          # gdk-pixbuf override for linuxdeploy
│           └── tauri.conf.json
│
├── runtime/                         # Python AI sidecar
│   ├── main.py                      # FastAPI app + port negotiation
│   ├── config.py                    # pydantic-settings (reads ~/.config/opensarthi/.env)
│   ├── db.py                        # SQLite conversation history
│   ├── requirements.txt
│   ├── api/
│   │   └── websocket.py             # WebSocket router, agent execution, token tracking
│   ├── planner/
│   │   └── agent.py                 # PydanticAI agent + system prompt
│   ├── tools/                       # Desktop automation tools
│   ├── providers/                   # X11/Wayland desktop providers
│   ├── voice/
│   │   └── pipeline.py              # SpeechRecognition + echo protection
│   ├── memory/                      # LanceDB vector store
│   ├── observer/                    # Screenshot + OCR pipeline
│   ├── security/                    # bubblewrap sandboxing
│   ├── llm/                         # LLM provider wrappers
│   └── mcp/                         # Model Context Protocol server/client
│
├── package.json                     # pnpm workspace root
├── pnpm-workspace.yaml
└── README.md
```

---

## 🔮 Roadmap

- [ ] **Multi-turn Barge-In** — voice interrupt during active TTS playback
- [ ] **Local Model Preloading** — pre-fetch Ollama weights on sidecar launch to reduce TTFT
- [ ] **Wayland Window Tracking** — enhance `ydotool` window management for KDE/GNOME Wayland
- [ ] **Sandboxed bubblewrap Profiles** — user-configurable execution rules per app
- [ ] **MCP Server** — expose OpenSarthi tools as Model Context Protocol server
- [ ] **Desktop Overlays** — bounding-box highlights on elements the agent is interacting with
- [ ] **API Key Keyring** — migrate from plaintext `.env` to OS-level secret store (libsecret)

---

## 🔒 Security Model

- **Tauri v2 Capabilities** — frontend strictly scoped via granular permission files
- **bubblewrap Sandboxing** — shell commands run in `bwrap` with isolated filesystem
- **User Consent Dialogs** — any destructive action requires explicit user approval via UI
- **Config Isolation** — all user data lives in `~/.config/opensarthi/` (never in AppImage mounts)

---

## 📚 Further Reading

- [Runtime README](./runtime/README.md) — Python sidecar internals, voice pipeline, agent architecture
- [Desktop README](./apps/desktop/README.md) — Frontend components, theming, build process
- [CHANGELOG](./CHANGELOG.md) — Detailed history of all changes and fixes
