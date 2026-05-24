# OpenSarthi — Implementation Plan
## Part 3: Tool System — State-Aware Tools & ToolResult Contract

> **Priority:** P0 — Critical. Every other system depends on rich tool return values.
> **Affected files:** `runtime/planner/schemas.py` [REFACTOR], `runtime/tools/base.py` [REFACTOR], all individual tool files

---

## 1. Problem Statement

Current tools likely return something like:

```python
return {"success": True}
# or
return "Clicked successfully"
```

This is not enough. The agent needs to know:
- Did the click actually change the UI?
- Is it safe to proceed to the next step?
- If it failed, can it retry, or should it replan?
- What did the desktop look like after the action?

---

## 2. The ToolResult Contract

**Update: `runtime/planner/schemas.py`**

```python
from pydantic import BaseModel
from typing import Optional, Any
from enum import Enum

class ToolResultConfidence(str, Enum):
    HIGH   = "high"    # Action definitly worked
    MEDIUM = "medium"  # Action likely worked, unverified
    LOW    = "low"     # Action may have worked

class ToolResult(BaseModel):
    """
    Standard return type for ALL tools.
    Rich enough for the agent to decide: continue / retry / replan.
    """
    success: bool

    # What was observed after the action
    observation: Optional[str] = None          # Human-readable description
    ui_changed: Optional[bool] = None          # Did the screen change?
    active_window: Optional[str] = None        # Window title after action

    # Failure details
    error: Optional[str] = None                # Error message if failed
    retryable: bool = True                     # Can the step be retried?

    # Guidance for the agent
    confidence: ToolResultConfidence = ToolResultConfidence.MEDIUM
    suggested_next: Optional[str] = None       # e.g. "Now wait for Firefox to load"

    # Raw data (for debugging)
    raw_output: Optional[Any] = None

    @classmethod
    def ok(cls, observation: str = "Success", **kwargs) -> "ToolResult":
        return cls(success=True, observation=observation, **kwargs)

    @classmethod
    def fail(cls, error: str, retryable: bool = True, **kwargs) -> "ToolResult":
        return cls(success=False, error=error, retryable=retryable, **kwargs)
```

---

## 3. BaseTool Update

**Update: `runtime/tools/base.py`**

```python
from abc import ABC, abstractmethod
from typing import Any
from planner.schemas import ToolResult
from enum import Enum

class RiskLevel(str, Enum):
    SAFE      = "safe"       # read-only, view-only actions
    MODERATE  = "moderate"   # typing, clicking, file reads
    DANGEROUS = "dangerous"  # shell commands, file writes, system changes
    FORBIDDEN = "forbidden"  # never auto-execute

class BaseTool(ABC):
    name: str
    description: str          # Shown to LLM for tool selection
    risk_level: RiskLevel = RiskLevel.MODERATE

    @abstractmethod
    async def execute(self, args: dict) -> ToolResult:
        """Execute the tool and return a structured ToolResult."""
        ...

    async def safe_execute(self, args: dict, permission_manager=None) -> ToolResult:
        """Permission-checked execution wrapper."""
        if self.risk_level == RiskLevel.FORBIDDEN:
            return ToolResult.fail("This action is forbidden.", retryable=False)

        if self.risk_level == RiskLevel.DANGEROUS and permission_manager:
            approved = await permission_manager.request(self.name, args)
            if not approved:
                return ToolResult.fail("User denied permission.", retryable=False)

        try:
            return await self.execute(args)
        except Exception as e:
            return ToolResult.fail(str(e), retryable=True)
```

---

## 4. State-Aware Desktop Tools

**Update: `runtime/tools/desktop.py`**

The tools now take an optional `observer` to capture post-action state.

### Click Tool (State-Aware)

```python
class ClickTool(BaseTool):
    name = "click"
    description = "Click at (x, y) coordinates. Use click_element for semantic clicking."
    risk_level = RiskLevel.MODERATE

    async def execute(self, args: dict) -> ToolResult:
        x = args.get("x")
        y = args.get("y")
        button = args.get("button", "left")

        if x is None or y is None:
            return ToolResult.fail("Missing x or y coordinate", retryable=False)

        try:
            # Execute click
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "mousemove", str(x), str(y), "click", str({"left":1,"right":3,"middle":2}[button]),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=3)

            if proc.returncode != 0:
                return ToolResult.fail(
                    f"xdotool click failed: {stderr.decode()}",
                    retryable=True
                )

            return ToolResult.ok(
                observation=f"Clicked at ({x}, {y}) with {button} button",
                confidence=ToolResultConfidence.MEDIUM,
                suggested_next="Observe the desktop to verify the click had the intended effect"
            )

        except asyncio.TimeoutError:
            return ToolResult.fail("Click timed out", retryable=True)
        except Exception as e:
            return ToolResult.fail(str(e), retryable=True)


class TypeTextTool(BaseTool):
    name = "type_text"
    description = "Type text into the currently focused input field."
    risk_level = RiskLevel.MODERATE

    async def execute(self, args: dict) -> ToolResult:
        text = args.get("text", "")
        if not text:
            return ToolResult.fail("No text provided", retryable=False)

        try:
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "type", "--clearmodifiers", "--delay", "30", "--", text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)

            if proc.returncode != 0:
                return ToolResult.fail(f"xdotool type failed: {stderr.decode()}", retryable=True)

            return ToolResult.ok(
                observation=f"Typed: '{text[:50]}{'...' if len(text) > 50 else ''}'",
                confidence=ToolResultConfidence.HIGH
            )
        except Exception as e:
            return ToolResult.fail(str(e))


class OpenAppTool(BaseTool):
    name = "open_app"
    description = "Open an application by name (e.g. 'firefox', 'konsole', 'dolphin')."
    risk_level = RiskLevel.MODERATE

    async def execute(self, args: dict) -> ToolResult:
        app = args.get("app", "")
        if not app:
            return ToolResult.fail("No app name provided", retryable=False)

        try:
            proc = await asyncio.create_subprocess_exec(
                app, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
            )
            # Don't wait — app launches in background
            return ToolResult.ok(
                observation=f"Launched '{app}'",
                confidence=ToolResultConfidence.MEDIUM,
                suggested_next=f"Use wait_for_window('{app}') to confirm it opened"
            )
        except FileNotFoundError:
            return ToolResult.fail(f"App '{app}' not found on PATH", retryable=False)
        except Exception as e:
            return ToolResult.fail(str(e))
```

---

## 5. Shell Tool (Sandboxed)

```python
class ShellTool(BaseTool):
    name = "shell"
    description = "Execute a shell command inside a bubblewrap sandbox. Use for read-only operations."
    risk_level = RiskLevel.DANGEROUS

    # Blocked patterns — never execute these
    BLOCKED = [
        r"rm\s+-rf\s+/",
        r"mkfs\.",
        r"dd\s+if=.+of=/dev/",
        r":\(\)\{.*\}",  # fork bomb
        r"chmod\s+-R\s+777\s+/",
        r">\s*/dev/sd",
    ]

    async def execute(self, args: dict) -> ToolResult:
        import re
        command = args.get("command", "")
        timeout = args.get("timeout", 30)

        if not command:
            return ToolResult.fail("No command provided", retryable=False)

        # Safety check
        for pattern in self.BLOCKED:
            if re.search(pattern, command):
                return ToolResult.fail(
                    f"Blocked dangerous pattern in command: '{command}'",
                    retryable=False
                )

        bwrap_cmd = [
            "bwrap",
            "--ro-bind", "/usr", "/usr",
            "--ro-bind", "/bin", "/bin",
            "--ro-bind", "/lib", "/lib",
            "--ro-bind", "/lib64", "/lib64",
            "--ro-bind", "/etc", "/etc",
            "--bind", "/home", "/home",  # Allow home dir access
            "--proc", "/proc",
            "--dev", "/dev",
            "--tmpfs", "/tmp",
            "--unshare-all",
            "--share-net",
            "--die-with-parent",
            "--", "bash", "-c", command
        ]

        try:
            proc = await asyncio.create_subprocess_exec(
                *bwrap_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)

            if proc.returncode != 0:
                return ToolResult.fail(
                    stderr.decode()[:500],
                    retryable=False,
                    raw_output={"returncode": proc.returncode, "stderr": stderr.decode()}
                )

            output = stdout.decode()[:2000]  # Truncate large outputs
            return ToolResult.ok(
                observation=output if output else "(no output)",
                confidence=ToolResultConfidence.HIGH,
                raw_output={"returncode": 0, "stdout": output}
            )

        except asyncio.TimeoutError:
            return ToolResult.fail(f"Command timed out after {timeout}s", retryable=False)
        except Exception as e:
            return ToolResult.fail(str(e))
```

---

## 6. Tool Registry

```python
# tools/registry.py [REFACTOR]

from tools.desktop import ClickTool, TypeTextTool, OpenAppTool
from tools.system import ShellTool
from tools.wait_tools import WaitForWindowTool, WaitForTextTool

_registry: dict[str, BaseTool] = {}

def _register(*tools):
    for tool in tools:
        _registry[tool.name] = tool

# Register all tools
_register(
    ClickTool(),
    TypeTextTool(),
    OpenAppTool(),
    ShellTool(),
    WaitForWindowTool(),
    WaitForTextTool(),
)

def get(name: str) -> Optional[BaseTool]:
    return _registry.get(name)

def all_tools() -> list[BaseTool]:
    return list(_registry.values())

def get_schemas() -> list[dict]:
    """Return JSON schema list for PydanticAI tool registration."""
    return [
        {
            "name": t.name,
            "description": t.description,
        }
        for t in _registry.values()
    ]
```

---

## 7. Implementation Checklist

- [ ] Update `planner/schemas.py` with full `ToolResult` model
- [ ] Update `tools/base.py` with `BaseTool`, `RiskLevel`, `safe_execute()`
- [ ] Rewrite `tools/desktop.py` — ClickTool, TypeTextTool, OpenAppTool with ToolResult
- [ ] Rewrite `tools/system.py` — ShellTool with bubblewrap + blocked patterns
- [ ] Create `tools/wait_tools.py` — WaitForWindowTool, WaitForTextTool
- [ ] Update `tools/registry.py` with proper registration pattern
- [ ] Test each tool individually with a simple script before wiring into agent
- [ ] Add `psutil` to `requirements.txt`

---

## 8. Manual Testing Script

Create `tests/test_tools.py`:

```python
import asyncio
from tools.desktop import ClickTool, TypeTextTool, OpenAppTool
from tools.system import ShellTool

async def main():
    # Test 1: Open konsole
    r = await OpenAppTool().execute({"app": "konsole"})
    print("open_app:", r)

    await asyncio.sleep(2)

    # Test 2: Shell (safe command)
    r = await ShellTool().execute({"command": "echo hello from sandbox"})
    print("shell:", r)

    # Test 3: Shell (blocked command — should fail)
    r = await ShellTool().execute({"command": "rm -rf /"})
    print("shell blocked:", r)

asyncio.run(main())
```

---

> Next: [04_testing_strategy.md](./04_testing_strategy.md)
