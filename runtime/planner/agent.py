from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIModel
from typing import Any, Optional
import os

os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")

from config import settings
from tools.desktop import ClickTool, TypeTextTool, PressKeyTool, OpenAppTool, ClickElementTool
from tools.system import ShellTool
from tools.wait_tools import WaitForWindowTool, WaitForTextTool
from observation import DesktopSnapshot

# Configure LLMs
local_llm = OllamaModel(settings.local_model)
cloud_llm = local_llm

class AgentDependencies(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    require_cloud: bool = False
    log_action: Any = None

SYSTEM_PROMPT = """
You are OpenSarthi, an AI-powered Linux desktop agent.

You help users automate tasks on their desktop — opening apps, clicking buttons,
typing text, running commands, and more.

KEY RULES:
1. NEVER call tools that are not listed in the AVAILABLE TOOLS section.
   Do NOT use brave_search, web_search, google_search, or any tool not listed.
   
2. For desktop tasks, always follow this sequence:
   open_app → wait_for_window → interact
   
3. For conversational questions (no tools needed), respond in plain text ONLY.

4. Use the desktop state from the OPENSARTHI AGENT CONTEXT block to make decisions.

5. When generating plans:
   - Break tasks into small, concrete steps
   - Always use wait_for_window after open_app
   - Use shell tool to run terminal commands directly

6. RESPONSE FORMAT - STRICTLY FOLLOW THIS:
   - For tasks: ALWAYS output a ```json code block with a JSON array. Nothing else.
   - For conversation: plain text only.

TASK EXAMPLE:
User: "Open Chrome and search for YouTube"
Response:
```json
[
  {"tool": "open_app", "args": {"app": "google-chrome"}, "description": "Open Google Chrome"},
  {"tool": "wait_for_window", "args": {"title": "Chrome"}, "description": "Wait for Chrome to load"},
  {"tool": "type_text", "args": {"text": "youtube.com"}, "description": "Type youtube.com in address bar"},
  {"tool": "press_key", "args": {"key": "Return"}, "description": "Press Enter to navigate"}
]
```

SHELL COMMAND EXAMPLE:
User: "Run garuda-update"
Response:
```json
[
  {"tool": "shell", "args": {"command": "garuda-update", "timeout": 120}, "description": "Run garuda-update to update the system"}
]
```
"""

agent = Agent(
    model=local_llm,
    deps_type=AgentDependencies,
    system_prompt=SYSTEM_PROMPT,
)

def _args_hint(tool) -> str:
    """Generate a short argument description for tools."""
    if tool.name == "click":
        return "x: int, y: int, button?: str"
    elif tool.name == "type_text":
        return "text: str"
    elif tool.name == "press_key":
        return "key: str"
    elif tool.name == "open_app":
        return "app: str"
    elif tool.name == "click_element":
        return "role: str, name: str"
    elif tool.name == "shell":
        return "command: str"
    elif tool.name == "wait_for_window":
        return "title: str, timeout?: float"
    elif tool.name == "wait_for_text":
        return "text: str, timeout?: float"
    return "..."

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
    from tools.registry import all_tools
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
