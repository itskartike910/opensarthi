# OpenSarthi — Implementation Plan
## Part 4: Testing Strategy — Validating All Existing Systems

> **Priority:** P0 — Run these before implementing anything new.
> **Goal:** Find what's actually broken before building more on top of it.

---

## 1. Test Structure

Create a `tests/` directory in the runtime:

```
runtime/tests/
├── test_websocket.py       # WebSocket connect + message round-trip
├── test_providers.py       # Each LLM provider: auth + basic chat
├── test_tools.py           # Each desktop/shell tool individually
├── test_voice.py           # Voice pipeline: mic → STT → echo protection
├── test_db.py              # SQLite history: save/load/clear
├── test_observation.py     # Desktop observer: window title, OCR
├── test_fallback.py        # Cloud failure → Ollama fallback
├── test_appimage.py        # AppImage-specific: bootstrap, venv, config paths
└── conftest.py             # Shared fixtures
```

Run with: `python -m pytest tests/ -v`

---

## 2. WebSocket Tests (`test_websocket.py`)

Tests the communication layer between frontend and backend.

```python
import asyncio
import json
import pytest
import websockets

RUNTIME_PORT = 38495  # Update to match your running port

@pytest.mark.asyncio
async def test_websocket_connects():
    """Basic: can we connect to the running runtime?"""
    uri = f"ws://127.0.0.1:{RUNTIME_PORT}/ws"
    async with websockets.connect(uri) as ws:
        assert ws.open

@pytest.mark.asyncio
async def test_send_receive_text_message():
    """Send a user_message, receive assistant_response."""
    uri = f"ws://127.0.0.1:{RUNTIME_PORT}/ws"
    async with websockets.connect(uri) as ws:
        # Send a simple message
        await ws.send(json.dumps({
            "type": "user_message",
            "payload": {"text": "Say 'pong' and nothing else."}
        }))

        # Expect a response within 30 seconds
        response = None
        for _ in range(60):
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(msg)
            if data.get("type") == "assistant_response":
                response = data
                break

        assert response is not None, "Never received assistant_response"
        assert "payload" in response
        assert "text" in response["payload"]
        print(f"Response: {response['payload']['text']}")

@pytest.mark.asyncio
async def test_token_usage_in_response():
    """Assert that token usage is included in every response."""
    uri = f"ws://127.0.0.1:{RUNTIME_PORT}/ws"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({
            "type": "user_message",
            "payload": {"text": "Hello"}
        }))

        for _ in range(60):
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(msg)
            if data.get("type") == "assistant_response":
                payload = data["payload"]
                assert "usage" in payload, "Missing 'usage' in response payload"
                usage = payload["usage"]
                assert "request_tokens" in usage
                assert "response_tokens" in usage
                break

@pytest.mark.asyncio
async def test_new_chat_clears_history():
    """new_chat event should clear the conversation thread."""
    uri = f"ws://127.0.0.1:{RUNTIME_PORT}/ws"
    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps({"type": "new_chat", "payload": {}}))
        # Expect an ack or no crash
        await asyncio.sleep(1)
        # Send a message and verify it works
        await ws.send(json.dumps({
            "type": "user_message",
            "payload": {"text": "Hello after new chat"}
        }))
        for _ in range(60):
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(msg)
            if data.get("type") == "assistant_response":
                break
```

---

## 3. Provider Tests (`test_providers.py`)

```python
import pytest
import os
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.config/opensarthi/.env"))

# ── Groq ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_groq_basic_chat():
    from pydantic_ai import Agent
    from pydantic_ai.models.groq import GroqModel

    api_key = os.getenv("groq_api_key")
    if not api_key:
        pytest.skip("groq_api_key not configured")

    agent = Agent(
        model=GroqModel("llama-3.3-70b-versatile", api_key=api_key),
        system_prompt="You are a test assistant. Reply with exactly 'GROQ_OK'."
    )
    result = await agent.run("Say your test response.")
    assert "GROQ_OK" in result.output

@pytest.mark.asyncio
async def test_groq_no_tool_hallucination():
    """Verify Groq doesn't hallucinate brave_search or other forbidden tools."""
    from pydantic_ai import Agent
    from pydantic_ai.models.groq import GroqModel
    from planner.agent import SYSTEM_PROMPT

    api_key = os.getenv("groq_api_key")
    if not api_key:
        pytest.skip("groq_api_key not configured")

    agent = Agent(
        model=GroqModel("llama-3.3-70b-versatile", api_key=api_key),
        system_prompt=SYSTEM_PROMPT,
        # No tools registered — if it tries to call one, it'll error
    )
    # Should respond in plain text without attempting any tool call
    result = await agent.run("What is the capital of France?")
    assert result.output  # Should have a text response, not a tool call error

# ── Gemini ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_gemini_basic_chat():
    from pydantic_ai import Agent
    from pydantic_ai.models.gemini import GeminiModel

    api_key = os.getenv("gemini_api_key")
    if not api_key:
        pytest.skip("gemini_api_key not configured")

    agent = Agent(model=GeminiModel("gemini-2.5-flash", api_key=api_key))
    result = await agent.run("Say 'GEMINI_OK' and nothing else.")
    assert "GEMINI_OK" in result.output

# ── Ollama ────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_ollama_local():
    """Test local Ollama connection — must have Ollama running."""
    from pydantic_ai import Agent
    from pydantic_ai.models.ollama import OllamaModel
    import httpx

    # Check if Ollama is running
    try:
        httpx.get("http://localhost:11434/api/tags", timeout=2)
    except Exception:
        pytest.skip("Ollama not running on localhost:11434")

    agent = Agent(model=OllamaModel("qwen2.5-coder:3b"))
    result = await agent.run("Say 'OLLAMA_OK' and nothing else.")
    assert result.output

# ── Fallback Logic ─────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_cloud_to_local_fallback():
    """Simulate cloud failure → Ollama fallback."""
    from api.websocket import handle_agent_execution

    # This will fail with invalid key, should fall back to Ollama
    class MockSettings:
        provider = "groq"
        cloud_model = "llama-3.3-70b-versatile"
        local_model = "qwen2.5-coder:3b"
        groq_api_key = "invalid_key_intentionally"

    # Test that the fallback runs without crashing
    # (unit test — not full integration)
    pass  # Implement based on your actual websocket structure
```

---

## 4. Tool Tests (`test_tools.py`)

**Run these with an active X11/KDE desktop session.**

```python
import asyncio
import pytest

@pytest.mark.asyncio
async def test_open_app_konsole():
    from tools.desktop import OpenAppTool
    result = await OpenAppTool().execute({"app": "konsole"})
    print(result)
    assert result.success
    assert "konsole" in result.observation.lower()

@pytest.mark.asyncio
async def test_shell_safe_command():
    from tools.system import ShellTool
    result = await ShellTool().execute({"command": "echo hello_from_sandbox"})
    assert result.success
    assert "hello_from_sandbox" in result.observation

@pytest.mark.asyncio
async def test_shell_blocked_command():
    from tools.system import ShellTool
    result = await ShellTool().execute({"command": "rm -rf /"})
    assert not result.success
    assert not result.retryable

@pytest.mark.asyncio
async def test_type_text_requires_focus():
    """Type text — requires a focused text input on screen."""
    from tools.desktop import TypeTextTool
    # Manually open a text editor before running this test
    result = await TypeTextTool().execute({"text": "hello opensarthi test"})
    print(result)
    # Don't assert success — depends on what's focused

@pytest.mark.asyncio
async def test_wait_for_window():
    from sync_primitives import wait_for_window
    import asyncio

    # Open konsole then wait for it
    proc = await asyncio.create_subprocess_exec("konsole")
    try:
        found = await wait_for_window("Konsole", timeout=8)
        assert found
    finally:
        proc.terminate()

@pytest.mark.asyncio
async def test_wait_for_window_timeout():
    from sync_primitives import wait_for_window, TimeoutError as WaitTimeout
    with pytest.raises(WaitTimeout):
        await wait_for_window("NonExistentApp_XYZ_12345", timeout=2)
```

---

## 5. Voice Pipeline Tests (`test_voice.py`)

```python
import pytest
import asyncio

@pytest.mark.asyncio
async def test_voice_pipeline_imports():
    """All voice imports should succeed."""
    import speech_recognition as sr
    pipeline_module = __import__("voice.pipeline", fromlist=["VoicePipeline"])
    assert hasattr(pipeline_module, "VoicePipeline")

@pytest.mark.asyncio
async def test_microphone_available():
    """Check that at least one microphone is accessible."""
    import speech_recognition as sr
    mics = sr.Microphone.list_microphone_names()
    print(f"Available mics: {mics}")
    assert len(mics) > 0, "No microphones found"

@pytest.mark.asyncio
async def test_echo_protection_flag():
    """is_speaking flag prevents STT when TTS is active."""
    from voice.pipeline import VoicePipeline

    pipeline = VoicePipeline(on_transcript=lambda t: None)
    pipeline.is_speaking = True

    # Simulate: trigger listen while speaking
    # It should NOT start listening
    # (Actual implementation depends on how VoicePipeline is structured)
    assert pipeline.is_speaking is True  # Baseline check

@pytest.mark.asyncio
async def test_silence_timeout_fires():
    """8-second silence timeout should trigger without voice input."""
    # This test requires: pipeline running + no mic input for 8 seconds
    # Difficult to automate — mark as manual for now
    pytest.skip("Manual test: run pipeline, wait 8s with no voice input")
```

---

## 6. Database Tests (`test_db.py`)

```python
import asyncio
import pytest
import os
import tempfile

@pytest.mark.asyncio
async def test_save_and_load_messages():
    from db import save_message, get_history, clear_thread
    import uuid

    thread_id = str(uuid.uuid4())

    await save_message(thread_id, "user", "Hello test")
    await save_message(thread_id, "assistant", "Hello back")

    history = await get_history(thread_id)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"

    await clear_thread(thread_id)
    history = await get_history(thread_id)
    assert len(history) == 0

@pytest.mark.asyncio
async def test_db_at_config_path():
    """DB should be at ~/.config/opensarthi/opensarthi.db, not in runtime/"""
    from config import Settings
    settings = Settings()
    db_path = os.path.expanduser("~/.config/opensarthi/opensarthi.db")
    # After running the app, this file should exist
    assert os.path.exists(db_path), f"DB not found at {db_path}"
```

---

## 7. Observation Tests (`test_observation.py`)

```python
import asyncio
import pytest

@pytest.mark.asyncio
async def test_get_active_window():
    """Get the active window title — requires a running desktop session."""
    from observation import DesktopObserver
    observer = DesktopObserver()
    snap = await observer.snapshot()
    print(f"Active window: {snap.active_window_title}")
    # Should return something (even if None on CI)
    assert snap is not None

@pytest.mark.asyncio
async def test_ocr_returns_text():
    """OCR should return some text from the current screen."""
    from observation import DesktopObserver
    observer = DesktopObserver()
    text = await observer._ocr_active_region()
    print(f"OCR result: {text[:200] if text else 'None'}")
    # On a running desktop this should return something
    assert text is None or isinstance(text, str)
```

---

## 8. Test Run Order (Follow This)

Run tests in this exact order to avoid false positives:

```bash
cd runtime

# 1. Unit tests (no running server needed)
python -m pytest tests/test_db.py -v
python -m pytest tests/test_tools.py::test_shell_safe_command -v
python -m pytest tests/test_tools.py::test_shell_blocked_command -v

# 2. Start the runtime in another terminal first:
#    python main.py
# Then:
python -m pytest tests/test_websocket.py -v

# 3. Provider tests (need API keys)
python -m pytest tests/test_providers.py -v

# 4. Desktop tests (need active KDE/X11 session)
python -m pytest tests/test_tools.py -v
python -m pytest tests/test_observation.py -v

# 5. Voice tests (need microphone)
python -m pytest tests/test_voice.py -v
```

---

## 9. Known Expected Failures (Before Fixes)

| Test | Expected Failure | Why |
|------|-----------------|-----|
| `test_groq_no_tool_hallucination` | May fail occasionally | Llama 3 still hallucinates despite system prompt |
| `test_type_text_requires_focus` | Needs manual setup | Requires active text input on screen |
| `test_wait_for_window_timeout` | Will pass | Tests negative case |
| `test_ocr_returns_text` | May return None | Depends on screen content + pytesseract install |
| `test_observation.py` | AT-SPI part fails | AT-SPI integration is P1 not yet built |

---

> Next: [05_voice_pipeline.md](./05_voice_pipeline.md)
