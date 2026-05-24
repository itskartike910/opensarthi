from typing import Optional
from tools.base import BaseTool
from tools.desktop import ClickTool, TypeTextTool, PressKeyTool, OpenAppTool, ClickElementTool
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
    PressKeyTool(),
    OpenAppTool(),
    ClickElementTool(),
    ShellTool(),
    WaitForWindowTool(),
    WaitForTextTool(),
)

def get(name: str) -> Optional[BaseTool]:
    return _registry.get(name)

def all_tools() -> list[BaseTool]:
    return list(_registry.values())

def get_schemas() -> list[dict]:
    """Return JSON schema list for tool registration."""
    return [
        {
            "name": t.name,
            "description": t.description,
        }
        for t in _registry.values()
    ]
