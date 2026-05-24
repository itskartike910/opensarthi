# OpenSarthi — Implementation Plan
## Part 2: Observation System & Synchronization Primitives

> **Priority:** P0 — Critical. The agent is blind without this.
> **Affected files:** `runtime/observation.py` [NEW], `runtime/sync_primitives.py` [NEW], `runtime/tools/desktop.py` [REFACTOR]

---

## 1. Problem Statement

Currently, after a tool executes (e.g., `click(x, y)`), the agent has **zero feedback**:
- Did the click land on the right element?
- Did the UI change?
- Did an app open?
- Did a loading spinner appear and then disappear?

Without observation, the agent is guessing. Every action must be followed by a desktop state snapshot.

---

## 2. Desktop Observer (`runtime/observation.py`)

The `DesktopObserver` collects the desktop state from multiple sources and merges them into a single structured snapshot.

```python
import asyncio
import time
import subprocess
from dataclasses import dataclass, field
from typing import Optional
import mss
import pytesseract
from PIL import Image
import io

@dataclass
class DesktopSnapshot:
    """A point-in-time snapshot of the desktop state."""
    timestamp: float = field(default_factory=time.time)
    active_window_title: Optional[str] = None
    active_window_pid: Optional[int] = None
    focused_element_role: Optional[str] = None
    focused_element_text: Optional[str] = None
    screen_text_summary: Optional[str] = None   # OCR on visible area
    accessibility_tree: Optional[dict] = None    # AT-SPI tree (when available)
    screenshot_path: Optional[str] = None        # Saved to /tmp for LLM vision
    error: Optional[str] = None

    def to_prompt_context(self) -> str:
        """Format snapshot as a text block for the LLM prompt."""
        lines = [
            f"DESKTOP STATE (at {self.timestamp:.1f}):",
            f"  Active Window: {self.active_window_title or 'unknown'}",
            f"  Focused Element: {self.focused_element_role or 'none'} — '{self.focused_element_text or ''}'",
        ]
        if self.screen_text_summary:
            lines.append(f"  Visible Text (OCR): {self.screen_text_summary[:300]}")
        return "\n".join(lines)


class DesktopObserver:
    """
    Collects desktop state snapshots. Uses:
    - wmctrl/xdotool for active window info (X11)
    - AT-SPI for accessibility tree (when available)
    - mss + pytesseract for screenshot OCR (fallback)
    """

    def __init__(self):
        self._display = self._detect_display()

    def _detect_display(self) -> str:
        import os
        if os.environ.get("WAYLAND_DISPLAY"):
            return "wayland"
        return "x11"

    async def snapshot(self) -> DesktopSnapshot:
        snap = DesktopSnapshot()

        # 1. Active window
        try:
            snap.active_window_title = await self._get_active_window_title()
        except Exception as e:
            snap.error = f"window_title: {e}"

        # 2. Focused element via AT-SPI (best effort)
        try:
            role, text = await self._get_focused_element()
            snap.focused_element_role = role
            snap.focused_element_text = text
        except Exception:
            pass  # AT-SPI not available, skip

        # 3. OCR on center-screen region for text context
        try:
            snap.screen_text_summary = await self._ocr_active_region()
        except Exception:
            pass

        return snap

    async def _get_active_window_title(self) -> Optional[str]:
        if self._display == "x11":
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "getactivewindow", "getwindowname",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
            return stdout.decode().strip() or None
        return None  # Wayland: implement via D-Bus portal later

    async def _get_focused_element(self) -> tuple[Optional[str], Optional[str]]:
        """Get AT-SPI focused element. Requires PyGObject."""
        try:
            import gi
            gi.require_version("Atspi", "2.0")
            from gi.repository import Atspi

            desktop = Atspi.get_desktop(0)
            focused = Atspi.get_desktop(0)
            # Walk the AT-SPI tree to find focused element
            # (full implementation in 07_accessibility_integration.md)
            return None, None
        except ImportError:
            return None, None

    async def _ocr_active_region(self) -> Optional[str]:
        """Capture center 800x600 of screen and run OCR."""
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary display
            # Capture center region only (faster than full screen)
            region = {
                "left": monitor["left"] + monitor["width"] // 4,
                "top": monitor["top"] + monitor["height"] // 4,
                "width": monitor["width"] // 2,
                "height": monitor["height"] // 2,
            }
            img = sct.grab(region)
            pil_img = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")

        # Run OCR in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(
            None,
            pytesseract.image_to_string,
            pil_img,
            "eng"  # language
        )
        # Clean up whitespace and truncate
        cleaned = " ".join(text.split())[:500]
        return cleaned if cleaned else None
```

---

## 3. Synchronization Primitives (`runtime/sync_primitives.py`)

These are the **most critical missing tools** for real desktop automation.

```python
import asyncio
import time
from typing import Callable, Optional, Any
from dataclasses import dataclass

class TimeoutError(Exception):
    pass

class WaitConditionError(Exception):
    pass


async def poll_until(
    condition: Callable[[], Any],
    timeout: float = 10.0,
    interval: float = 0.5,
    description: str = "condition"
) -> Any:
    """
    Poll a callable until it returns a truthy value or timeout expires.
    
    Example:
        result = await poll_until(
            lambda: check_element_exists("Submit"),
            timeout=10,
            description="Submit button to appear"
        )
    """
    deadline = time.monotonic() + timeout
    last_error = None

    while time.monotonic() < deadline:
        try:
            result = condition()
            if asyncio.iscoroutine(result):
                result = await result
            if result:
                return result
        except Exception as e:
            last_error = e

        await asyncio.sleep(interval)

    raise TimeoutError(
        f"Timed out after {timeout}s waiting for: {description}. "
        f"Last error: {last_error}"
    )


async def wait_for_window(
    title_contains: str,
    timeout: float = 10.0,
    observer=None
) -> bool:
    """
    Wait until a window with a matching title appears.
    
    Example:
        await wait_for_window("Firefox", timeout=8)
    """
    import subprocess

    async def check():
        try:
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "search", "--name", title_contains,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=1)
            return bool(stdout.decode().strip())
        except Exception:
            return False

    return await poll_until(
        check,
        timeout=timeout,
        description=f"window containing '{title_contains}'"
    )


async def wait_for_text_visible(
    text: str,
    timeout: float = 10.0,
    observer=None
) -> bool:
    """
    Wait until specific text appears on screen (via OCR).
    
    Example:
        await wait_for_text_visible("Login successful", timeout=15)
    """
    if observer is None:
        from observation import DesktopObserver
        observer = DesktopObserver()

    async def check():
        snap = await observer.snapshot()
        screen_text = snap.screen_text_summary or ""
        return text.lower() in screen_text.lower()

    return await poll_until(
        check,
        timeout=timeout,
        interval=1.0,
        description=f"text '{text}' to appear on screen"
    )


async def wait_for_process(
    process_name: str,
    timeout: float = 15.0
) -> bool:
    """
    Wait until a process with the given name is running.
    
    Example:
        await wait_for_process("firefox", timeout=10)
    """
    async def check():
        proc = await asyncio.create_subprocess_exec(
            "pgrep", "-x", process_name,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=1)
        return bool(stdout.decode().strip())

    return await poll_until(
        check,
        timeout=timeout,
        description=f"process '{process_name}' to start"
    )


async def wait_for_network_idle(
    timeout: float = 10.0,
    check_interval: float = 1.0
) -> bool:
    """
    Wait until no significant network activity (heuristic: no new TCP connections).
    Useful after clicking buttons that trigger API calls.
    """
    import psutil

    async def check():
        connections_before = len(psutil.net_connections(kind="tcp"))
        await asyncio.sleep(check_interval)
        connections_after = len(psutil.net_connections(kind="tcp"))
        # "idle" = connection count stable
        return abs(connections_after - connections_before) <= 2

    return await poll_until(
        check,
        timeout=timeout,
        description="network to become idle"
    )
```

---

## 4. Adding Wait Tools to the Tool Registry

These sync primitives become **callable agent tools**:

```python
# tools/wait_tools.py [NEW]

from pydantic_ai import RunContext
from sync_primitives import wait_for_window, wait_for_text_visible, wait_for_process
from planner.schemas import ToolResult

async def tool_wait_for_window(ctx: RunContext, title: str, timeout: float = 10.0) -> ToolResult:
    """Wait until a window with the given title appears."""
    try:
        await wait_for_window(title, timeout=timeout)
        return ToolResult(success=True, observation=f"Window '{title}' appeared")
    except TimeoutError as e:
        return ToolResult(success=False, error=str(e), retryable=False)

async def tool_wait_for_text(ctx: RunContext, text: str, timeout: float = 10.0) -> ToolResult:
    """Wait until specific text is visible on screen."""
    try:
        await wait_for_text_visible(text, timeout=timeout)
        return ToolResult(success=True, observation=f"Text '{text}' visible on screen")
    except TimeoutError as e:
        return ToolResult(success=False, error=str(e), retryable=True)
```

**Register in `planner/agent.py`:**

```python
agent = Agent(
    ...
    tools=[
        # existing tools
        tool_click,
        tool_type_text,
        tool_open_app,
        tool_shell,
        # NEW wait tools
        tool_wait_for_window,
        tool_wait_for_text,
    ]
)
```

---

## 5. Verification Pattern

After every action, the agent should verify the outcome. This is the observation→verify pattern:

```python
# In agent_runtime.py — _execute_step()

async def _execute_step(self, step: PlanStep, index: int) -> ToolResult:
    result = await tool.execute(step.args)

    if result.success and step.verify_with:
        # Step has a post-condition to verify
        await self._transition(AgentState.OBSERVING)
        verified = await self._verify_postcondition(step.verify_with)
        if not verified:
            return ToolResult(
                success=False,
                error=f"Action appeared to succeed but verification failed: {step.verify_with}",
                retryable=True
            )

    return result
```

**PlanStep gains a `verify_with` field** (see `08_prompting_architecture.md`):

```python
class PlanStep(BaseModel):
    tool: str
    args: dict
    description: str
    verify_with: Optional[str] = None  # e.g. "Firefox window appears"
    wait_after: Optional[float] = None # seconds to wait after execution
    retryable: bool = True
```

---

## 6. Implementation Checklist

- [ ] Create `runtime/observation.py` with `DesktopObserver` and `DesktopSnapshot`
- [ ] Test `DesktopObserver.snapshot()` on your KDE/X11 system
- [ ] Create `runtime/sync_primitives.py` with all wait functions
- [ ] Create `runtime/tools/wait_tools.py` wrapping sync primitives as PydanticAI tools
- [ ] Register wait tools in `planner/agent.py`
- [ ] Add `verify_with` field to `PlanStep` schema
- [ ] Implement `_verify_postcondition()` in `AgentRuntime`
- [ ] Add `psutil` to `requirements.txt` (for `wait_for_network_idle`)
- [ ] Test observation on: open Firefox, observe window title change, type in URL bar, observe text

---

> Next: [03_tool_system.md](./03_tool_system.md)
