# OpenSarthi Desktop Shell

This is the native frontend shell for the OpenSarthi AI agent, built using **Tauri v2**, **React 19**, and **TypeScript**.

---

## 🎨 UI, Themes, & Resizable Layouts

The interface is designed to be a lightweight, borderless, floating overlay that stays out of your way until needed, providing maximum layout flexibility:

* **Leetcode-Style Mouse Drag Resizing**: Built a pure React mouse drag-and-resize engine coordinating Left, Middle, and Right grid panels:
  - Drag handlers update pane layouts dynamically inside [AssistantOverlay.tsx](./src/components/assistant/AssistantOverlay.tsx).
  - Explicit size constraints protect visual structure (Left Panel: `180px - 450px`, Right Panel: `160px - 400px`).
* **Interactive Glowing Splitters**: Leverages `.panel-splitter` divider elements in `globals.css` that light up in beautiful, fluid glass glows matching the active theme's accent color on hover and drag actions.
* **5 Curated Premium Themes**:
  - `Glass Red-Black` (Default High-Tech)
  - `Forest Green-Black` (Cyberpunk Green)
  - `Deep Purple-Black` (Midnight Tech)
  - `Cyber Sky-White` (Modern Minimalist Light)
  - `Sakura Pink-White` (Warm Soft Light)
* **Fluid Micro-Animations**: Utilizing `framer-motion` to coordinate real-time audio waveforms, pulsing recording rings, expanded settings, and sliding shell logs.
* **Zustand State Engine**: Fully manages Voice States, Chat Logs, Active Presets, Shell execution intercept lists, and resizer state cache.

---

## 🔌 Core Integrations

Because this is a Tauri application, the React frontend has native capabilities that a standard web app does not:
* **System Tray**: A native OS tray icon allows you to show/hide the assistant globally.
* **Sidecar Management**: The Rust core is configured to automatically spawn and manage the lifecycle of the Python AI runtime (`opensarthi-runtime`).
* **IPC (Inter-Process Communication)**: Custom Rust-to-Frontend events are used for port negotiation, screenshot captures, and global hotkey triggers.

---

## 📦 Production Packaging & Build

To compile a final optimized production Linux AppImage, execute the specialized build command:

```bash
PATH="/mnt/kartik/ai_desktop_agent_assistant/opensarthi/apps/desktop/src-tauri/mock_pkg_config:$PATH" \
NO_STRIP=true \
APPIMAGE_EXTRACT_AND_RUN=1 \
pnpm run build
```

### Build Details
- Runs typechecks on all TypeScript/React components.
- Builds static UI files via Vite.
- Bypasses WebKit2GTK symbol strip limitations on standard Linux environments by setting `NO_STRIP=true` and custom mocking path hooks.
- Compiles Rust native hooks.
- Spits out a single standalone bundle under:
  `src-tauri/target/release/bundle/appimage/OpenSarthi_0.1.0_amd64.AppImage`

---

## 🛠️ Development

To start the UI in development mode:

```bash
# Ensure you are in the apps/desktop directory or running from the monorepo root via pnpm
pnpm install
pnpm dev
```

*Note: The frontend will attempt to connect to the Python runtime via WebSocket. Ensure the backend is running and has printed its dynamically assigned port to the console so the Tauri sidecar listener can pick it up.*

---

## 🔒 Tauri v2 Permissions Configuration

We use Tauri v2's strict capability system. The permissions are explicitly mapped out in `src-tauri/capabilities/main.json`. 
The frontend is only allowed to perform specific OS functions (like reading clipboard, firing notifications, and reading the screen buffer), ensuring a secure boundary between the UI and the host system.

---

## 🔮 What's Left (Roadmap)

- [ ] **Saved Panel Width Cache**: Persist customized draggable panel width preferences inside LocalStorage to load layouts on app relaunch.
- [ ] **Tray Icon Theme Sync**: Match the color of the native Linux top tray icon with the selected active color scheme dynamically.
- [ ] **Overlay Drag & Drop**: Enable drag-and-dropping files directly into the conversation panel for quick multi-modal AI analysis.
