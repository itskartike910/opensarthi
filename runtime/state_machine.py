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
