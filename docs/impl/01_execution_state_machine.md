# OpenSarthi — Implementation Plan
## Part 1: Execution State Machine & Agent Loop

> **Priority:** P0 — Critical. Everything else depends on this.
> **Affected files:** `runtime/state_machine.py` [NEW], `runtime/agent_runtime.py` [NEW], `runtime/api/websocket.py` [REFACTOR]

---

## 1. Problem Statement

The current agent loop in `api/websocket.py` is:

```python
result = await agent.run(text, deps=self.deps, model=active_model, message_history=...)
await self.send_message("assistant_response", {...})
```

This is a **single-shot LLM call**. There is no:
- State the UI can react to (planning, executing, waiting...)
- Retry logic per step
- Observation after tool calls
- Cancellation support
- Replanning when a step fails

---

## 2. AgentState Enum

**Create: `runtime/state_machine.py`**

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import time

class AgentState(str, Enum):
    IDLE             = "idle"
    LISTENING        = "listening"        # voice pipeline active
    PLANNING         = "planning"         # LLM generating plan
    EXECUTING        = "executing"        # running a tool step
    WAITING          = "waiting"          # wait_for_element / polling
    OBSERVING        = "observing"        # taking accessibility/screenshot snapshot
    RETRYING         = "retrying"         # step failed, attempting retry
    ASKING_PERMISSION = "asking_permission"  # dangerous action needs user approval
    ERROR            = "error"            # unrecoverable failure
    COMPLETE         = "complete"         # goal achieved

@dataclass
class AgentStateContext:
    state: AgentState = AgentState.IDLE
    current_goal: Optional[str] = None
    current_step_index: int = 0
    current_step_description: Optional[str] = None
    total_steps: int = 0
    retry_count: int = 0
    max_retries: int = 3
    error_message: Optional[str] = None
    started_at: float = field(default_factory=time.time)
    last_transition: float = field(default_factory=time.time)

    def transition(self, new_state: AgentState, **kwargs):
        """Transition to a new state, updating metadata."""
        self.state = new_state
        self.last_transition = time.time()
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "goal": self.current_goal,
            "step": self.current_step_index,
            "step_description": self.current_step_description,
            "total_steps": self.total_steps,
            "retry_count": self.retry_count,
            "error": self.error_message,
        }
```

---

## 3. WebSocket State Events

Every state transition must be broadcast to the frontend immediately.

**Update: `runtime/api/websocket.py`**

```python
async def emit_state(self, state_ctx: AgentStateContext):
    """Broadcast current agent state to the frontend UI."""
    await self.send_message("agent_state", state_ctx.to_dict())
```

### Frontend Message Types (add to `useWebSocket.ts`)

```typescript
// New message type from backend
type AgentStatePayload = {
  state: "idle"|"listening"|"planning"|"executing"|"waiting"|
         "observing"|"retrying"|"asking_permission"|"error"|"complete";
  goal: string | null;
  step: number;
  step_description: string | null;
  total_steps: number;
  retry_count: number;
  error: string | null;
}
```

The UI should show the state in the right panel ("Live Plan & Activity"):
- `planning` → animated spinner + "Analyzing goal..."
- `executing` → step progress indicator
- `waiting` → "Waiting for UI..." with elapsed timer
- `retrying` → "Retry 1/3..." with reason

---

## 4. The Agent Execution Engine

**Create: `runtime/agent_runtime.py`**

This is the central orchestrator. It replaces the current `agent.run()` one-liner.

```python
import asyncio
import time
from typing import Optional
from pydantic_ai import Agent
from state_machine import AgentState, AgentStateContext
from planner.schemas import Plan, PlanStep, ToolResult
from observation import DesktopObserver

class AgentRuntime:
    """
    The stateful execution engine for OpenSarthi.
    Replaces the single agent.run() call with a proper
    observe → plan → execute → verify → retry loop.
    """

    def __init__(self, ws_handler, agent: Agent, observer: DesktopObserver):
        self.ws = ws_handler
        self.agent = agent
        self.observer = observer
        self.state = AgentStateContext()
        self._cancel_requested = False

    async def run(self, goal: str, model, deps, message_history: list) -> str:
        """
        Main entry point. Accepts a user goal and runs the full
        plan → execute → verify loop.
        Returns the final response string.
        """
        self._cancel_requested = False
        self.state = AgentStateContext(current_goal=goal)

        try:
            # 1. Take an initial observation of the desktop
            await self._transition(AgentState.OBSERVING)
            initial_observation = await self.observer.snapshot()

            # 2. Plan
            await self._transition(AgentState.PLANNING)
            plan = await self._plan(goal, initial_observation, message_history, model, deps)

            if plan is None:
                # Pure conversational response (no tool steps)
                return self.state.error_message or "No plan generated."

            self.state.total_steps = len(plan.steps)

            # 3. Execute each step
            for i, step in enumerate(plan.steps):
                if self._cancel_requested:
                    break

                await self._transition(
                    AgentState.EXECUTING,
                    current_step_index=i,
                    current_step_description=step.description
                )

                result = await self._execute_step(step, i)

                if not result.success:
                    if result.retryable and self.state.retry_count < self.state.max_retries:
                        await self._retry(step, result)
                    else:
                        await self._transition(
                            AgentState.ERROR,
                            error_message=f"Step {i} failed: {result.error}"
                        )
                        return f"❌ Failed at step {i}: {step.description}\nReason: {result.error}"

                # Post-step observation
                await self._transition(AgentState.OBSERVING)
                post_obs = await self.observer.snapshot()
                await self.ws.emit_state(self.state)

            # 4. Complete
            await self._transition(AgentState.COMPLETE)
            return plan.final_response or "Task completed."

        except asyncio.CancelledError:
            await self._transition(AgentState.IDLE)
            raise
        except Exception as e:
            await self._transition(AgentState.ERROR, error_message=str(e))
            raise
        finally:
            # Always return to IDLE after a short delay
            await asyncio.sleep(1.5)
            await self._transition(AgentState.IDLE)

    async def _transition(self, new_state: AgentState, **kwargs):
        self.state.transition(new_state, **kwargs)
        await self.ws.emit_state(self.state)

    async def _plan(self, goal: str, observation: dict, history: list, model, deps) -> Optional["Plan"]:
        """Call the LLM with structured context to generate a Plan."""
        from planner.agent import build_structured_context
        context = build_structured_context(goal, observation, history)
        result = await self.agent.run(context, deps=deps, model=model, message_history=history)
        return result.output  # Should be a Plan object (see Part 3 / 08_prompting_architecture)

    async def _execute_step(self, step: "PlanStep", index: int) -> ToolResult:
        """Execute a single plan step and return a ToolResult."""
        from tools.registry import tool_registry
        tool = tool_registry.get(step.tool)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {step.tool}",
                retryable=False
            )
        return await tool.execute(step.args)

    async def _retry(self, step: "PlanStep", last_result: ToolResult):
        """Handle a retryable failure."""
        self.state.retry_count += 1
        await self._transition(
            AgentState.RETRYING,
            current_step_description=f"Retrying: {step.description} ({self.state.retry_count}/{self.state.max_retries})"
        )
        await asyncio.sleep(1.5)  # Brief pause before retry

    def request_cancel(self):
        """Signal the execution loop to stop after current step."""
        self._cancel_requested = True
```

---

## 5. Integrating Into websocket.py

Replace the current `handle_user_message` agent execution block:

```python
# BEFORE (current)
result = await agent.run(text, deps=self.deps, model=active_model, message_history=message_history)

# AFTER
from agent_runtime import AgentRuntime
from observation import DesktopObserver

observer = DesktopObserver()  # instantiate once at WS session level
runtime = AgentRuntime(ws_handler=self, agent=agent, observer=observer)
final_response = await runtime.run(
    goal=text,
    model=active_model,
    deps=self.deps,
    message_history=message_history
)
```

---

## 6. Cancellation Support (Frontend → Backend)

Add a new WebSocket message type to support user-initiated stop:

```python
# websocket.py — process_incoming
elif msg_type == "cancel_execution":
    if hasattr(self, '_current_runtime') and self._current_runtime:
        self._current_runtime.request_cancel()
        await self.send_message("agent_state", {"state": "idle", "goal": None})
```

```typescript
// Frontend — send cancel
ws.send(JSON.stringify({ type: "cancel_execution", payload: {} }))
```

---

## 7. Frontend State Visualization

Update `AssistantOverlay.tsx` right panel to render state:

| State | Right Panel Display |
|-------|-------------------|
| `idle` | "// READY" in dim text |
| `planning` | Animated dots + "Analyzing goal..." |
| `executing` | Step N/M progress bar + step description |
| `waiting` | Spinning indicator + "Waiting for UI response..." + elapsed seconds |
| `retrying` | "⚠ Retrying step N (attempt X/3)" |
| `observing` | "👁 Observing desktop state..." |
| `asking_permission` | Permission dialog component |
| `error` | Red text + error message |
| `complete` | "✓ Task complete" |

---

## 8. Implementation Checklist

- [ ] Create `runtime/state_machine.py` with `AgentState` enum and `AgentStateContext`
- [ ] Create `runtime/agent_runtime.py` with `AgentRuntime` class
- [ ] Add `emit_state()` method to WebSocket handler
- [ ] Update `websocket.py` to use `AgentRuntime.run()` instead of `agent.run()`
- [ ] Add `agent_state` message type handling in `useWebSocket.ts`
- [ ] Update right panel in `AssistantOverlay.tsx` to render state
- [ ] Add `cancel_execution` message handler
- [ ] Add Cancel button in the UI (visible during executing/waiting states)

---

> Next: [02_observation_system.md](./02_observation_system.md)
