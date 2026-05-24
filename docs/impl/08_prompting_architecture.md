# OpenSarthi — Implementation Plan
## Part 8: Prompting Architecture — Structured Agent Context

> **Priority:** P0 — Critical. Better prompting = fewer hallucinations and more reliable tool use.
> **Affected files:** `runtime/planner/agent.py` [REFACTOR], `runtime/planner/schemas.py` [UPDATE]

---

## 1. Current Problem

The agent currently receives only a conversation history:

```python
result = await agent.run(
    user_text,
    message_history=last_20_messages  # That's it
)
```

The LLM has no idea:
- What the current desktop state looks like
- What tools are available and what each does
- What actions have already been tried and failed
- What step it's on in a multi-step plan
- What permissions it has

This makes tool use unreliable and forces the model to guess.

---

## 2. Structured Context Block

Every agent invocation should begin with a rich context block injected as a user message (not system prompt — system prompts don't accept dynamic runtime state well):

```
OPENSARTHI AGENT CONTEXT
════════════════════════════════════════════════

GOAL:
  Open Firefox and navigate to github.com

CURRENT DESKTOP STATE:
  Active Window: Konsole - /home/kartikk
  Focused Element: [terminal] ''
  Visible Text: "kartikk@..."

EXECUTION CONTEXT:
  Step: 1 of 3
  Previous Actions: (none)
  Failed Actions: (none)
  Retry Count: 0

AVAILABLE TOOLS:
  • open_app(app: str) — Open an application by name
  • click(x: int, y: int, button?: str) — Click at coordinates
  • click_element(role: str, name?: str) — Semantic click via AT-SPI
  • type_text(text: str) — Type text into focused element
  • shell(command: str) — Run a sandboxed shell command
  • wait_for_window(title: str, timeout?: float) — Wait for a window to appear
  • wait_for_text(text: str, timeout?: float) — Wait for text to appear on screen

PERMISSIONS:
  SAFE: open_app, click, type_text, wait_*
  REQUIRES CONFIRMATION: shell

CONSTRAINTS:
  • Only call tools listed above — no others
  • After open_app, always use wait_for_window before interacting with it
  • Report what you observe after each tool call
  • If a step fails twice, ask the user for help

════════════════════════════════════════════════
INSTRUCTIONS:
Generate a step-by-step plan as a JSON array of tool calls to achieve the GOAL.
Each step: { "tool": "...", "args": {...}, "description": "..." }
```

---

## 3. Context Builder Function

**Update: `runtime/planner/agent.py`**

```python
from planner.schemas import AgentContext, PlanStep
from observation import DesktopSnapshot
from tools.registry import all_tools

def build_structured_context(
    goal: str,
    snapshot: DesktopSnapshot,
    history: list,
    current_step: int = 0,
    total_steps: int = 0,
    previous_actions: list[str] = None,
    failed_actions: list[str] = None,
    retry_count: int = 0,
) -> str:
    """
    Build the structured context string injected before every agent call.
    This replaces loose conversational history as the agent's primary input.
    """

    # Desktop state section
    desktop_state_lines = []
    if snapshot.active_window_title:
        desktop_state_lines.append(f"  Active Window: {snapshot.active_window_title}")
    if snapshot.focused_element_role:
        desktop_state_lines.append(
            f"  Focused Element: [{snapshot.focused_element_role}] '{snapshot.focused_element_text or ''}'"
        )
    if snapshot.accessibility_tree and snapshot.accessibility_tree.get("summary"):
        summary = snapshot.accessibility_tree["summary"][:400]
        desktop_state_lines.append(f"  UI Elements:\n    {summary.replace(chr(10), chr(10)+'    ')}")
    elif snapshot.screen_text_summary:
        desktop_state_lines.append(f"  Screen Text: {snapshot.screen_text_summary[:200]}")
    desktop_state = "\n".join(desktop_state_lines) or "  (not available)"

    # Execution context section
    execution_lines = []
    if total_steps > 0:
        execution_lines.append(f"  Step: {current_step + 1} of {total_steps}")
    if previous_actions:
        for action in previous_actions[-5:]:  # Last 5 actions
            execution_lines.append(f"  ✓ {action}")
    if failed_actions:
        for action in failed_actions[-3:]:  # Last 3 failures
            execution_lines.append(f"  ✗ FAILED: {action}")
    if retry_count > 0:
        execution_lines.append(f"  Retry Count: {retry_count}")
    execution_ctx = "\n".join(execution_lines) or "  (none)"

    # Tools section
    tools = all_tools()
    tool_lines = [
        f"  • {t.name}({_args_hint(t)}) — {t.description}"
        for t in tools
    ]
    tools_section = "\n".join(tool_lines)

    # Permissions section
    from tools.base import RiskLevel
    safe = [t.name for t in tools if t.risk_level == RiskLevel.SAFE]
    confirm = [t.name for t in tools if t.risk_level == RiskLevel.DANGEROUS]
    perm_lines = []
    if safe:
        perm_lines.append(f"  SAFE (no confirmation): {', '.join(safe)}")
    if confirm:
        perm_lines.append(f"  REQUIRES CONFIRMATION: {', '.join(confirm)}")
    permissions = "\n".join(perm_lines) or "  (all safe)"

    context = f"""OPENSARTHI AGENT CONTEXT
════════════════════════════════════════════════

GOAL:
  {goal}

CURRENT DESKTOP STATE:
{desktop_state}

EXECUTION CONTEXT:
{execution_ctx}

AVAILABLE TOOLS:
{tools_section}

PERMISSIONS:
{permissions}

CONSTRAINTS:
  • Only call tools listed above — do NOT invent tools like brave_search
  • After open_app, always use wait_for_window before interacting with it
  • After each click or type, describe what you expect to happen next
  • If a step fails twice with the same error, report it and stop
  • For dangerous tools (shell), describe the full command before executing

════════════════════════════════════════════════
Based on the above context, generate the next action or respond to the user.
If this requires multiple steps, output a JSON plan array.
"""
    return context


def _args_hint(tool) -> str:
    """Generate a short arg hint string for a tool."""
    # This would use the tool's parameter schema in a full implementation
    return "..."
```

---

## 4. Plan Schema with Full Detail

**Update: `runtime/planner/schemas.py`**

```python
from pydantic import BaseModel
from typing import Optional, Any, List
from enum import Enum

class ToolResultConfidence(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"

class ToolResult(BaseModel):
    success: bool
    observation: Optional[str] = None
    ui_changed: Optional[bool] = None
    active_window: Optional[str] = None
    error: Optional[str] = None
    retryable: bool = True
    confidence: ToolResultConfidence = ToolResultConfidence.MEDIUM
    suggested_next: Optional[str] = None
    raw_output: Optional[Any] = None

    @classmethod
    def ok(cls, observation: str = "Success", **kwargs) -> "ToolResult":
        return cls(success=True, observation=observation, **kwargs)

    @classmethod
    def fail(cls, error: str, retryable: bool = True, **kwargs) -> "ToolResult":
        return cls(success=False, error=error, retryable=retryable, **kwargs)


class PlanStep(BaseModel):
    tool: str                            # Tool name from registry
    args: dict                           # Tool arguments
    description: str                     # Human-readable description of this step
    verify_with: Optional[str] = None   # Post-condition: text/window to verify
    wait_after: Optional[float] = None  # Seconds to wait after execution
    retryable: bool = True
    depends_on: List[int] = []          # Step indices this depends on


class Plan(BaseModel):
    goal: str
    steps: List[PlanStep]
    final_response: Optional[str] = None   # Text response after all steps
    recovery_hint: Optional[str] = None    # What to do if plan fails


class AgentContext(BaseModel):
    """Full context passed to the agent on each invocation."""
    goal: str
    snapshot: Optional[dict] = None         # Serialized DesktopSnapshot
    current_step: int = 0
    total_steps: int = 0
    previous_actions: List[str] = []
    failed_actions: List[str] = []
    retry_count: int = 0
    conversation_history: List[dict] = []   # Last N messages
```

---

## 5. System Prompt Update

The current system prompt should be updated to reflect the structured context format:

```python
SYSTEM_PROMPT = """
You are OpenSarthi, an AI-powered Linux desktop agent.

You help users automate tasks on their desktop — opening apps, clicking buttons,
typing text, running commands, and more.

KEY RULES:
1. NEVER call tools that are not listed in the AVAILABLE TOOLS section of your context.
   This includes brave_search, web_search, google_search, or any web tool.
   
2. For desktop tasks, always follow this sequence:
   - Open app → wait_for_window → interact → verify
   
3. For conversational questions (no tools needed), respond in plain text.

4. If you receive a structured OPENSARTHI AGENT CONTEXT block, use it to inform
   your decisions. The desktop state shows exactly what the user can see.

5. When generating plans:
   - Break complex tasks into small, verifiable steps
   - Each step should have a clear verify_with condition
   - Use wait_* tools after opening apps or clicking buttons that trigger loading
   
6. If asked about something you can't do with available tools, say so clearly.
   Do not invent capabilities.

RESPONSE FORMAT:
- For tasks: output a JSON array of PlanStep objects (see schema in context)
- For conversation: output plain text
- For clarification needed: ask a specific question
"""
```

---

## 6. Integrating Context Into Agent Run

**Update `runtime/api/websocket.py`** (inside the `AgentRuntime` call):

```python
# In AgentRuntime._plan():

async def _plan(self, goal: str, snapshot: DesktopSnapshot, history: list, model, deps) -> Optional[Plan]:
    from planner.agent import build_structured_context

    # Build the structured context block
    context = build_structured_context(
        goal=goal,
        snapshot=snapshot,
        history=history,
        current_step=self.state.current_step_index,
        total_steps=self.state.total_steps,
        previous_actions=[],   # Populate from execution log
        failed_actions=[],
        retry_count=self.state.retry_count
    )

    # The context becomes the "user message" sent to the LLM
    # History is still included for conversational continuity
    result = await self.agent.run(
        context,
        deps=deps,
        model=model,
        message_history=history
    )

    return result.output
```

---

## 7. Handling Both Conversational and Task Responses

The LLM sometimes needs to respond conversationally (no tools), sometimes with a plan.

Detect the response type:

```python
def parse_agent_response(raw_output: Any) -> tuple[Optional[Plan], Optional[str]]:
    """
    Parse the agent output as either a Plan (task) or plain text (conversation).
    Returns (plan, text_response) — one will be None.
    """
    import json

    if isinstance(raw_output, Plan):
        return raw_output, None

    if isinstance(raw_output, str):
        # Try to parse as JSON plan
        text = raw_output.strip()
        if text.startswith("[") or text.startswith("{"):
            try:
                data = json.loads(text)
                if isinstance(data, list):
                    steps = [PlanStep(**s) for s in data]
                    return Plan(goal="", steps=steps), None
            except Exception:
                pass
        # Plain text response
        return None, text

    return None, str(raw_output)
```

---

## 8. Implementation Checklist

- [ ] Update `planner/schemas.py` with full `PlanStep`, `Plan`, `AgentContext`, `ToolResult`
- [ ] Create `build_structured_context()` in `planner/agent.py`
- [ ] Update system prompt to reflect new structured format
- [ ] Update `AgentRuntime._plan()` to pass structured context
- [ ] Implement `parse_agent_response()` to handle plan vs. text responses
- [ ] Test with Groq: send a task message, verify it produces a JSON plan
- [ ] Test with Ollama: verify fallback still produces usable text
- [ ] Test conversational: "What is Python?" should get plain text, not a plan
- [ ] Test task: "Open Firefox" should produce a plan with open_app + wait_for_window steps

---

## 9. Example Expected Plan Output

For the goal: "Open Firefox and go to github.com"

```json
[
  {
    "tool": "open_app",
    "args": {"app": "firefox"},
    "description": "Launch Firefox browser",
    "verify_with": "Firefox",
    "wait_after": 0.5,
    "retryable": true
  },
  {
    "tool": "wait_for_window",
    "args": {"title": "Firefox", "timeout": 10},
    "description": "Wait for Firefox to open",
    "retryable": false
  },
  {
    "tool": "click_element",
    "args": {"role": "entry", "name": "Search or enter address"},
    "description": "Click the address bar",
    "retryable": true
  },
  {
    "tool": "type_text",
    "args": {"text": "github.com\n"},
    "description": "Type the URL and press Enter",
    "verify_with": "github.com",
    "retryable": true
  }
]
```

---

> This completes the 8-part implementation plan.
> **Start from Part 1** and work forward. Do not skip to voice/wake word (Parts 5-6) until Parts 1-4 are working.
