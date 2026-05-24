from tools.base import BaseTool, RiskLevel
from planner.schemas import ToolResult, ToolResultConfidence
from sync_primitives import wait_for_window, wait_for_text_visible, TimeoutError

class WaitForWindowTool(BaseTool):
    name = "wait_for_window"
    description = "Wait until a window with the given title appears. Args: title (string), timeout (number, default 10.0)"
    risk_level = RiskLevel.SAFE

    async def execute(self, args: dict) -> ToolResult:
        title = args.get("title")
        timeout = float(args.get("timeout", 10.0))

        if not title:
            return ToolResult.fail("Missing title parameter", retryable=False)

        try:
            await wait_for_window(title, timeout=timeout)
            return ToolResult(
                success=True,
                observation=f"Window '{title}' appeared",
                confidence=ToolResultConfidence.HIGH
            )
        except TimeoutError as e:
            return ToolResult.fail(str(e), retryable=False)
        except Exception as e:
            return ToolResult.fail(str(e), retryable=True)


class WaitForTextTool(BaseTool):
    name = "wait_for_text"
    description = "Wait until specific text is visible on screen. Args: text (string), timeout (number, default 10.0)"
    risk_level = RiskLevel.SAFE

    async def execute(self, args: dict) -> ToolResult:
        text = args.get("text")
        timeout = float(args.get("timeout", 10.0))

        if not text:
            return ToolResult.fail("Missing text parameter", retryable=False)

        try:
            await wait_for_text_visible(text, timeout=timeout)
            return ToolResult(
                success=True,
                observation=f"Text '{text}' visible on screen",
                confidence=ToolResultConfidence.HIGH
            )
        except TimeoutError as e:
            return ToolResult.fail(str(e), retryable=True)
        except Exception as e:
            return ToolResult.fail(str(e), retryable=True)
