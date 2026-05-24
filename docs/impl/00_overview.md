# OpenSarthi — Agent Runtime Stabilization: Implementation Plan
## Overview & Priority Map

> **Current Phase:** Agent Runtime Stabilization (NOT new feature addition)
> **Goal:** Transform OpenSarthi from "LLM wrapper with tools" into "stateful desktop execution engine with AI planning"

---

## Document Index

This plan is split across multiple files to stay within editor limits. Read in order.

| File | Topic | Priority |
|------|-------|----------|
| [01_execution_state_machine.md](./01_execution_state_machine.md) | Agent state machine + execution loop | **P0 — Critical** |
| [02_observation_system.md](./02_observation_system.md) | Observation, verification, retries | **P0 — Critical** |
| [03_tool_system.md](./03_tool_system.md) | State-aware tools + result contracts | **P0 — Critical** |
| [04_testing_strategy.md](./04_testing_strategy.md) | Testing all existing systems end-to-end | **P0 — Critical** |
| [05_voice_pipeline.md](./05_voice_pipeline.md) | Streaming STT, wake word, VAD, barge-in | **P2 — Voice** |
| [06_wake_word_settings.md](./06_wake_word_settings.md) | Custom wake word UI + multi-word support | **P2 — Voice** |
| [07_accessibility_integration.md](./07_accessibility_integration.md) | AT-SPI tree, focused element, UI parsing | **P1 — Desktop** |
| [08_prompting_architecture.md](./08_prompting_architecture.md) | Structured agent prompting + context | **P0 — Critical** |

---

## What Is Already Working (Do Not Rebuild)

```
✅ Tauri v2 shell + React 19 frontend
✅ Rust sidecar management (sidecar.rs, tray.rs, ipc.rs)
✅ Python FastAPI + uvicorn runtime
✅ WebSocket communication + reconnect
✅ Multi-provider LLM (Groq, Gemini, OpenAI, Anthropic, OpenRouter, Ollama)
✅ Provider fallback (cloud → local no-tools agent)
✅ SQLite conversation history + 20-message sliding window
✅ Token usage tracking (request + response + session)
✅ Settings persistence (~/.config/opensarthi/.env)
✅ 5 premium themes + cyberpunk HUD
✅ AppImage packaging with bundled uv
✅ LD_LIBRARY_PATH isolation for AppImage Python
✅ Stale venv detection + auto-bootstrap
✅ Echo protection + silence timeout in voice pipeline
✅ PydanticAI agent with system prompt + Groq tool fix
```

---

## What Is Weak / Missing (The Plan)

```
❌ Agent execution loop (no observe → plan → execute → verify → retry cycle)
❌ Execution state machine (no formal IDLE/PLANNING/EXECUTING/WAITING states)
❌ Observation system (no post-action verification)
❌ Waiting/synchronization primitives (wait_for_element, wait_for_window)
❌ State-aware tools (tools are direct commands, not state-aware)
❌ ToolResult contracts (weak success/fail returns)
❌ Structured agent prompting (no GOAL+STATE+OBSERVATIONS context block)
❌ AT-SPI accessibility tree integration (architecture exists, not implemented)
❌ Streaming STT + wake word activation (SpeechRecognition is prototype-level)
❌ Custom wake word UI in settings
❌ End-to-end integration tests for existing systems
❌ Wayland automation stability
```

---

## Priority Order (Strict)

### P0 — Do These First (Unblocks Everything)

1. **Execution State Machine** → gives UI/voice/tool execution a shared contract
2. **ToolResult Contract** → every tool returns rich structured data
3. **Structured Prompting** → agent receives GOAL + STATE + OBSERVATIONS, not just history
4. **Observation Loop** → verify after every action
5. **Wait/Sync Primitives** → `wait_for_element`, `wait_for_window`, polling

### P1 — Desktop Understanding (After P0)

6. **AT-SPI Accessibility Tree** → primary UI understanding layer (not screenshots alone)
7. **Screenshot Observer** → fallback for apps without accessibility
8. **OCR Integration** → text extraction from screenshots

### P2 — Voice Pipeline Maturity

9. **faster-whisper streaming** → replace SpeechRecognition with local model
10. **Wake word + custom wake words** → OpenWakeWord + UI to configure
11. **VAD (Voice Activity Detection)** → smarter mic control
12. **Barge-in** → interrupt TTS mid-speech

### P3 — Automation Reliability

13. **X11 tool stability** → tested xdotool wrappers with retry
14. **Wayland abstraction** → mark experimental, document fallbacks

---

## What NOT To Build Right Now

> Stop until execution reliability improves:

- ❌ More AI providers
- ❌ New themes or UI panels
- ❌ Additional settings fields
- ❌ MCP server/client
- ❌ Desktop overlays
- ❌ Workflow templates

---

## Key Architecture Shift

### Before (current)

```
User message
→ PydanticAI agent.run()
→ LLM generates response + optional tool calls
→ Tools execute
→ Response sent to UI
```

### After (target)

```
User message or voice trigger
→ Set state: PLANNING
→ Build structured context (GOAL + CURRENT_STATE + OBSERVATIONS + HISTORY)
→ LLM generates plan (structured PlanStep list)
→ Set state: EXECUTING
→ For each step:
    → Execute tool
    → Collect ToolResult (success, observation, ui_changed, confidence)
    → If wait needed: Set state: WAITING → poll until condition met
    → Observe desktop state (accessibility snapshot / screenshot)
    → Verify step succeeded
    → If failed + retryable: Set state: RETRYING → replan
    → If permission needed: Set state: ASKING_PERMISSION → await user
→ Set state: COMPLETE
→ Emit structured response to UI
→ Set state: IDLE
```

---

## File / Module Map (Python Runtime Changes)

```
runtime/
├── agent_runtime.py         [NEW] Central execution engine
├── state_machine.py         [NEW] AgentState enum + transitions
├── observation.py           [NEW] Desktop state collector (AT-SPI + screenshot)
├── sync_primitives.py       [NEW] wait_for_element, wait_for_window, poll_until
├── planner/
│   ├── agent.py             [REFACTOR] Structured context builder + plan schema
│   └── schemas.py           [REFACTOR] PlanStep, ToolResult, AgentContext
├── tools/
│   ├── base.py              [REFACTOR] BaseTool with ToolResult contract
│   ├── desktop.py           [REFACTOR] State-aware input tools
│   └── system.py            [REFACTOR] bubblewrap shell tools
├── voice/
│   ├── pipeline.py          [REFACTOR] Replace SpeechRecognition with faster-whisper
│   ├── wakeword.py          [NEW] OpenWakeWord with configurable phrases
│   └── vad.py               [NEW] Voice Activity Detection
└── api/
    └── websocket.py         [REFACTOR] Emit agent state events to UI
```

---

## Timeline Estimate

| Phase | Work | Estimated Sessions |
|-------|------|-------------------|
| P0: State machine + ToolResult | Core architecture | 2 sessions |
| P0: Structured prompting | Prompt engineering | 1 session |
| P0: Observation + wait/sync | New modules | 2 sessions |
| P0: Integration testing | Test all existing systems | 2 sessions |
| P1: AT-SPI accessibility | Platform integration | 3 sessions |
| P2: Voice pipeline | faster-whisper + wakeword | 2 sessions |
| P3: Automation reliability | X11/Wayland testing | 1 session |

**Total: ~13 sessions to reach production-grade agent runtime**

---

> Start with [01_execution_state_machine.md](./01_execution_state_machine.md)
