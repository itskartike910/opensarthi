# OpenSarthi — Desktop Frontend

The Tauri v2 + React 19 desktop shell for OpenSarthi. Provides the UI, theming, voice controls, settings management, and real-time WebSocket connection to the Python AI runtime.

---

## 🖥️ Tech Stack

| Layer | Technology |
|-------|-----------|
| **Desktop Framework** | Tauri v2 |
| **UI Framework** | React 19 + TypeScript |
| **Bundler** | Vite 6 |
| **Styling** | Vanilla CSS with custom design tokens |
| **State Management** | Zustand |
| **WebSocket** | Native browser WebSocket with reconnect logic |
| **Icons** | Lucide React |

---

## 🎨 UI Design

### Cyberpunk HUD Layout

The main window uses a three-panel grid layout:

```
┌────────────────┬──────────────────────────┬────────────────┐
│  ACTIVE TASKS  │    CHAT / MAIN VIEW      │  LIVE PLAN &   │
│                │                          │    ACTIVITY    │
│  (scrollable)  │  messages + voice input  │  (scrollable)  │
├────────────────┴──────────────────────────┴────────────────┤
│  AGENT STATUS & SYSTEMS │ SYSTEM BUILD / VERSION INFO      │
│  Provider, Model, Tokens│ Online status, time              │
└──────────────────────────────────────────────────────────────┘
```

### 5 Premium Themes

| Theme | Style |
|-------|-------|
| **Glass Red-Black** | Default — high-tech cyberpunk red |
| **Forest Green-Black** | Cyberpunk green terminal |
| **Deep Purple-Black** | Midnight tech purple |
| **Cyber Sky-White** | Modern minimalist light |
| **Sakura Pink-White** | Warm soft light |

---

## ✅ Completed Features

### AssistantOverlay (`components/assistant/AssistantOverlay.tsx`)

The main UI component. Key capabilities:

- **Real-time token counter** — `TOKEN USAGE` (current request) and `SESSION TOTAL` (cumulative), displayed in the bottom-left HUD panel. Resets on New Chat.
- **Provider & model display** — shows the active provider and selected cloud/local model
- **New Chat** — clears conversation history (calls `new_chat` WebSocket event), resets token counter
- **Chat history** — renders assistant markdown responses and user messages
- **Voice input** — animated microphone button with waveform pulse and state transitions (idle → listening → processing)

### Settings (`components/settings/SettingsView.tsx`)

Cascading three-step settings flow:

```
1. Select AI Provider   →   2. Select / Enter Model   →   3. API Key   →   Save
```

Supported providers and their model lists:

| Provider | Example Models |
|----------|---------------|
| Groq | `llama-3.3-70b-versatile`, `mixtral-8x7b-32768` |
| Google | `gemini-2.5-flash`, `gemini-2.0-flash` |
| OpenAI | `gpt-4o`, `gpt-4o-mini` |
| Anthropic | `claude-opus-4-5`, `claude-sonnet-4-5` |
| OpenRouter | Custom text input |
| Ollama | Custom text input (local) |

- Saving with an empty key retains the previously saved key (no accidental wipe)
- Keys stored individually per provider in `~/.config/opensarthi/.env`

### WebSocket Hook (`hooks/useWebSocket.ts`)

- Auto-connects to the Python runtime on the dynamically negotiated port
- Handles `assistant_response`, `error`, `plan_step`, `task_update` message types
- Extracts `usage.request_tokens`, `usage.response_tokens`, `usage.total_tokens` from each response
- Auto-reconnects with exponential backoff on disconnect

---

## 📂 Directory Structure

```
apps/desktop/
├── src/
│   ├── main.tsx                     # Vite entry point
│   ├── App.tsx                      # Root component, router, theme provider
│   ├── components/
│   │   ├── assistant/
│   │   │   ├── AssistantOverlay.tsx # Main HUD (3-panel layout + token display)
│   │   │   └── TaskList.tsx         # Active task list (left panel)
│   │   ├── execution/               # Plan step viewer (right panel)
│   │   ├── permissions/             # Permission confirmation dialogs
│   │   └── settings/
│   │       └── SettingsView.tsx     # Provider → Model → Key settings UI
│   ├── hooks/
│   │   └── useWebSocket.ts          # WebSocket connection + message handler
│   ├── stores/                      # Zustand state (assistant, audio, execution)
│   └── styles/                      # Global CSS, theme tokens, animations
│
├── src-tauri/
│   ├── src/
│   │   ├── lib.rs                   # App bootstrap, sidecar launch
│   │   ├── sidecar.rs               # Python process spawn + port read
│   │   ├── tray.rs                  # System tray icon and menu
│   │   └── ipc.rs                   # Tauri IPC command handlers
│   ├── binaries/
│   │   └── opensarthi-runtime-x86_64-unknown-linux-gnu   # Bash bootstrap script
│   ├── resources/
│   │   └── uv                       # Bundled uv binary (57MB, portable Python)
│   ├── mock_pkg_config/
│   │   └── pkgconf                  # gdk-pixbuf path override for AppImage builds
│   ├── capabilities/                # Tauri v2 permission scoping
│   └── tauri.conf.json              # Window config, resource bundling, AppImage target
│
├── package.json
├── vite.config.ts
└── tsconfig.json
```

---

## 🔧 Rust Core (`src-tauri/src/`)

| File | Responsibility |
|------|---------------|
| `lib.rs` | App entry — sets up window, tray, spawns sidecar |
| `sidecar.rs` | Spawns the bootstrap script, reads `PORT:xxxx` from stdout, forwards to frontend |
| `tray.rs` | System tray icon, right-click menu (Show/Hide/Quit) |
| `ipc.rs` | Tauri `invoke` command handlers (port forwarding, etc.) |

---

## 🏗️ Building

### Development

```bash
# From the repo root
pnpm dev
```

This starts Vite HMR, compiles the Rust debug binary, spawns the Python sidecar, and opens the window.

### Production AppImage

```bash
# From the repo root
PATH="$(pwd)/apps/desktop/src-tauri/mock_pkg_config:$PATH" \
NO_STRIP=true \
APPIMAGE_EXTRACT_AND_RUN=1 \
pnpm tauri build -b appimage
```

> **Why mock_pkg_config?**  
> The `linuxdeploy-plugin-gtk.sh` uses `pkg-config --variable=gdk_pixbuf_binarydir` to locate GTK loader directories. On Arch/Garuda Linux this returns a path that doesn't exist in the expected linuxdeploy format. The `mock_pkg_config/pkgconf` wrapper intercepts these specific queries, creates the expected directories in `/tmp/mock_usr/`, and passes all other queries through to the real `pkgconf`.

> **Why APPIMAGE_EXTRACT_AND_RUN?**  
> The `linuxdeploy` AppImage itself requires FUSE to mount. This flag tells it to extract and run instead, bypassing the FUSE requirement (which may not be available in build environments).

---

## 🎨 Theme System

Themes are CSS custom property sets applied to `:root`. Each theme defines:

```css
--primary-color        /* main accent (e.g. #ff1744 for red) */
--primary-glow         /* rgba glow version */
--bg-primary           /* main background */
--bg-secondary         /* panel backgrounds */
--bg-tertiary          /* elevated surfaces */
--text-primary         /* main text */
--text-secondary       /* muted/secondary text */
--border-color         /* panel borders */
--font-mono            /* monospace font for HUD labels */
```
