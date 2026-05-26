import asyncio
import time
import json
from typing import Optional, Any
from pydantic_ai import Agent
from state_machine import AgentState, AgentStateContext
from planner.schemas import Plan, PlanStep, ToolResult
from observation import DesktopObserver, DesktopSnapshot

class AgentRuntime:
    """
    The stateful execution engine for OpenSarthi.
    Replaces the single agent.run() call with a proper
    observe → plan → execute → verify → retry loop.
    """

    def __init__(self, ws_handler, agent: Agent, observer: DesktopObserver, deps=None):
        self.ws = ws_handler
        self.agent = agent
        self.observer = observer
        self.deps = deps
        self.state = AgentStateContext()
        self._cancel_requested = False
        self.last_usage = None

    async def run(self, goal: str, model, message_history: list) -> str:
        """
        Main entry point. Accepts a user goal and runs the full
        observe → plan → execute → verify → retry loop.
        Returns the final response string.
        """
        self._cancel_requested = False
        self.state = AgentStateContext(current_goal=goal)
        self.last_usage = None

        completed_actions = []
        failed_actions = []
        replanning_attempts = 0
        max_replanning_attempts = 5

        try:
            while replanning_attempts < max_replanning_attempts:
                if self._cancel_requested:
                    await self._transition(AgentState.IDLE)
                    return "Execution cancelled by user."

                # 1. Take an observation of the desktop
                await self._transition(AgentState.OBSERVING)
                snapshot = await self.observer.snapshot()

                # 2. Plan/Decide the next actions
                await self._transition(AgentState.PLANNING)
                
                # Build context with actual completed_actions and failed_actions
                from planner.agent import build_structured_context
                context = build_structured_context(
                    goal=goal,
                    snapshot=snapshot,
                    history=message_history,
                    current_step=len(completed_actions),
                    total_steps=len(completed_actions) + 1,
                    previous_actions=completed_actions,
                    failed_actions=failed_actions,
                    retry_count=replanning_attempts
                )

                # Call Agent
                result = await self.agent.run(context, deps=self.deps, model=model, message_history=message_history)
                self.last_usage = getattr(result, "usage", None)
                
                # Parse response
                plan, text_response = self._parse_response(result.output)

                if plan is None:
                    # Conversational response (no tool steps), meaning the agent thinks it is done or cannot proceed.
                    response = text_response or "I couldn't generate a plan or a response."
                    await self._transition(AgentState.COMPLETE)
                    return response

                # Send plan creation details to client
                import uuid
                plan_id = str(uuid.uuid4())
                steps_data = []
                for idx, s in enumerate(plan.steps):
                    steps_data.append({
                        "index": idx,
                        "tool": s.tool,
                        "args": s.args or {},
                        "description": s.description or s.tool,
                        "status": "pending"
                    })

                await self.ws.send_message("plan_created", {
                    "id": plan_id,
                    "goal": plan.goal or goal or "Executing Task",
                    "steps": steps_data,
                    "recovery_hint": plan.recovery_hint
                })

                self.state.total_steps = len(plan.steps)
                await self._transition(AgentState.PLANNING)

                # 3. Execute each step in the generated plan
                plan_failed = False
                for i, step in enumerate(plan.steps):
                    if self._cancel_requested:
                        break

                    await self._transition(
                        AgentState.EXECUTING,
                        current_step_index=i,
                        current_step_description=step.description,
                        retry_count=0
                    )

                    # Reset retry count for this step
                    step_success = False
                    self.state.retry_count = 0
                    while self.state.retry_count <= self.state.max_retries:
                        if self._cancel_requested:
                            break

                        result = await self._execute_step(step, i)

                        if result.success:
                            # Verify post-condition if specified
                            if step.verify_with:
                                await self._transition(AgentState.OBSERVING)
                                verified = await self._verify_postcondition(step.verify_with)
                                if not verified:
                                    result = ToolResult.fail(
                                        error=f"Post-condition verification failed: {step.verify_with}",
                                        retryable=True
                                    )
                                else:
                                    step_success = True
                                    break
                            else:
                                step_success = True
                                break

                        # Handle failure
                        if not result.success:
                            if result.retryable and self.state.retry_count < self.state.max_retries:
                                self.state.retry_count += 1
                                await self._transition(
                                    AgentState.RETRYING,
                                    current_step_description=f"Retrying: {step.description} ({self.state.retry_count}/{self.state.max_retries})"
                                )
                                await asyncio.sleep(1.5)  # Brief pause before retry
                            else:
                                # Step failed permanently or max retries reached
                                break

                    if step_success:
                        completed_actions.append(step.description or f"Executed tool: {step.tool}")
                        # Brief wait after step if specified
                        if step.wait_after:
                            await self._transition(AgentState.WAITING)
                            await asyncio.sleep(step.wait_after)
                    else:
                        # Record failure and trigger replanning
                        failed_actions.append(f"{step.description or step.tool} (Reason: {result.error})")
                        plan_failed = True
                        break

                if plan_failed:
                    replanning_attempts += 1
                    # Increment retry/attempt count in the overall state context
                    self.state.retry_count = replanning_attempts
                    await self._transition(
                        AgentState.RETRYING,
                        current_step_description="Replanning due to step failure..."
                    )
                    await asyncio.sleep(1.5)
                    continue  # Loop back to observe & replan

                # If all steps in the current plan completed successfully, loop back to let the agent verify if the goal is met.
                replanning_attempts += 1
                self.state.retry_count = replanning_attempts
                await self._transition(
                    AgentState.RETRYING,
                    current_step_description="Verifying task completion..."
                )
                await asyncio.sleep(1.0)

            # If we exceeded max replanning attempts, call AI one final time to explain the failure to the user!
            await self._transition(AgentState.ERROR, error_message="Task failed after maximum replanning attempts.")
            
            final_error_context = f"""OPENSARTHI TASK FAILURE SUMMARY
════════════════════════════════════════════════
The task has failed because the maximum number of replanning attempts was exceeded.

GOAL:
  {goal}

COMPLETED ACTIONS:
  {completed_actions}

FAILED ACTIONS:
  {failed_actions}
════════════════════════════════════════════════
Please explain to the user in a friendly, conversational manner why the task could not be completed and what went wrong. Do not output a JSON plan.
"""
            try:
                result = await self.agent.run(final_error_context, deps=self.deps, model=model, message_history=message_history)
                return result.output
            except Exception:
                return f"❌ Failed to complete the task.\n\nCompleted steps:\n" + \
                       "\n".join(f"- {a}" for a in completed_actions) + \
                       "\n\nFailed steps:\n" + \
                       "\n".join(f"- {f}" for f in failed_actions)

        except asyncio.CancelledError:
            await self._transition(AgentState.IDLE)
            raise
        except Exception as e:
            import structlog
            structlog.get_logger().error("System error during execution", exc_info=True)
            
            err_type = type(e).__name__
            err_msg = str(e).strip()
            
            # Re-raise network/API errors so websocket can trigger local fallback
            network_err_types = (
                "ConnectTimeout", "ReadTimeout", "WriteTimeout",
                "ConnectError", "RemoteProtocolError", "NetworkError",
                "UnexpectedStatus", "ModelHTTPError"
            )
            if not err_msg or err_type in network_err_types or "timeout" in err_msg.lower() or "connect" in err_msg.lower():
                await self._transition(AgentState.ERROR, error_message=f"{err_type}: API connection failed")
                raise  # Let websocket.py catch and fall back to local model
            
            await self._transition(AgentState.ERROR, error_message=err_msg or err_type)
            return f"❌ System error during execution: {err_msg or err_type}"
        finally:
            # Always return to IDLE after a short delay
            await asyncio.sleep(1.0)
            await self._transition(AgentState.IDLE)

    async def _transition(self, new_state: AgentState, **kwargs):
        self.state.transition(new_state, **kwargs)
        await self.ws.emit_state(self.state)

    async def _plan(self, goal: str, snapshot: DesktopSnapshot, history: list, model) -> tuple[Optional[Plan], Optional[str]]:
        """Call the LLM with structured context to generate a Plan or conversational response."""
        from planner.agent import build_structured_context
        context = build_structured_context(
            goal=goal,
            snapshot=snapshot,
            history=history,
            current_step=self.state.current_step_index,
            total_steps=self.state.total_steps,
            previous_actions=[],
            failed_actions=[],
            retry_count=self.state.retry_count
        )

        # Call Agent
        result = await self.agent.run(context, deps=self.deps, model=model, message_history=history)
        self.last_usage = getattr(result, "usage", None)
        
        # Parse result
        return self._parse_response(result.output)

    def _parse_response(self, raw_output: Any) -> tuple[Optional[Plan], Optional[str]]:
        """Parse raw agent output as either a Plan or a text response."""
        if isinstance(raw_output, Plan):
            return raw_output, None

        if isinstance(raw_output, str):
            text = raw_output.strip()
            import re
            
            # Extract and preserve <think> blocks for display, but strip them for JSON parsing
            think_blocks = re.findall(r'<think>([\s\S]*?)</think>', text)
            thinking_text = "\n\n".join(b.strip() for b in think_blocks if b.strip())
            
            # Strip <think>...</think> from the text for JSON extraction
            text_for_json = re.sub(r'<think>[\s\S]*?</think>', '', text).strip()
            
            # Try to extract JSON plan block using regex
            json_text = None
            
            # Check for ```json ... ``` blocks
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', text_for_json)
            if json_match:
                json_text = json_match.group(1).strip()
            else:
                # Check for standard ``` ... ``` with brackets
                json_match = re.search(r'```\s*(\[[\s\S]*?\]|\{[\s\S]*?\})\s*```', text_for_json)
                if json_match:
                    json_text = json_match.group(1).strip()
                else:
                    # Fallback to finding the first [ or { matching bracket pair
                    json_match = re.search(r'(\[[\s\S]*?\]|\{[\s\S]*?\})', text_for_json)
                    if json_match:
                        json_text = json_match.group(1).strip()

            if json_text:
                try:
                    data = json.loads(json_text)
                    
                    # Tool positional arg order for list-style args (some models like Llama send args as a list)
                    TOOL_ARG_ORDER = {
                        "open_app":        ["app"],
                        "click":           ["x", "y", "button"],
                        "type_text":       ["text"],
                        "press_key":       ["key"],
                        "shell":           ["command", "timeout"],
                        "wait_for_window": ["title", "timeout"],
                        "wait_for_text":   ["text", "timeout"],
                        "click_element":   ["role", "name"],
                        "focus_window":    ["title"],
                    }
                    
                    # Robust cleanup before pydantic validation
                    def _cleanup_step(s: dict) -> dict:
                        if "tool" not in s and "action" in s:
                            s["tool"] = s.pop("action")
                            
                        if "description" not in s and "comment" in s:
                            s["description"] = s.pop("comment")
                        elif "description" not in s:
                            s["description"] = ""
                        
                        # Convert list-style args to named dict: ["konsole"] → {"app": "konsole"}
                        if "args" not in s or s["args"] is None:
                            s["args"] = {}
                        elif isinstance(s["args"], list):
                            tool_name = s.get("tool", "")
                            arg_keys = TOOL_ARG_ORDER.get(tool_name, [])
                            s["args"] = {k: v for k, v in zip(arg_keys, s["args"])}
                        
                        return s
                        
                    if isinstance(data, list):
                        steps = [PlanStep(**_cleanup_step(s)) for s in data]
                        return Plan(goal="", steps=steps), None
                    elif isinstance(data, dict):
                        if "steps" in data:
                            data["steps"] = [_cleanup_step(s) for s in data["steps"]]
                            return Plan(**data), None
                        else:
                            # Single step plan
                            step = PlanStep(**_cleanup_step(data))
                            return Plan(goal="", steps=[step]), None
                except Exception as e:
                    import structlog
                    structlog.get_logger().error("Plan JSON parsed but validation failed", error=str(e), json_text=json_text)
            return None, raw_output

        return None, str(raw_output)

    async def _execute_step(self, step: PlanStep, index: int) -> ToolResult:
        """Execute a single plan step and return a ToolResult."""
        from tools.registry import get
        tool = get(step.tool)
        if tool is None:
            err_res = ToolResult(
                success=False,
                error=f"Unknown tool: {step.tool}",
                retryable=False
            )
            await self.ws.send_message("tool_error", {
                "index": index,
                "error": err_res.error
            })
            return err_res
        
        # Broadcast tool action starting
        await self.ws.send_message("tool_action", {
            "tool": step.tool,
            "description": step.description,
            "status": "running",
            "result": None
        })
        await self.ws.send_message("tool_started", {"index": index})

        res = await tool.safe_execute(step.args, permission_manager=self.ws)

        # Broadcast tool action completed
        await self.ws.send_message("tool_action", {
            "tool": step.tool,
            "description": step.description,
            "status": "success" if res.success else "error",
            "result": res.observation if res.success else res.error
        })

        if res.success:
            await self.ws.send_message("tool_completed", {
                "index": index,
                "result": res.observation
            })
        else:
            await self.ws.send_message("tool_error", {
                "index": index,
                "error": res.error or "Unknown error"
            })

        return res

    async def _verify_postcondition(self, verify_with: str) -> bool:
        """Verify the postcondition of a step."""
        from sync_primitives import wait_for_text_visible, wait_for_window, TimeoutError
        try:
            # Simple heuristic matching
            if "window" in verify_with.lower() or "app" in verify_with.lower():
                # Extract title
                title = verify_with.split()[-1]
                await wait_for_window(title, timeout=5.0)
                return True
            else:
                await wait_for_text_visible(verify_with, timeout=5.0, observer=self.observer)
                return True
        except TimeoutError:
            return False
        except Exception:
            return False

    def request_cancel(self):
        """Signal the execution loop to stop after the current step."""
        self._cancel_requested = True
