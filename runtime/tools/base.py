from abc import ABC, abstractmethod
from typing import Any, Optional
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
            approved = await permission_manager.request_permission(self.name, args)
            if not approved:
                return ToolResult.fail("User denied permission.", retryable=False)

        try:
            import inspect
            sig = inspect.signature(self.execute)
            if 'permission_manager' in sig.parameters:
                return await self.execute(args, permission_manager=permission_manager)
            return await self.execute(args)
        except Exception as e:
            return ToolResult.fail(str(e), retryable=True)
