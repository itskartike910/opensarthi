from pydantic import BaseModel, ConfigDict
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.models.openai import OpenAIModel
from httpx import AsyncClient
import os

os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")


from pydantic_ai.providers.openai import OpenAIProvider
from config import settings
from tools.desktop import DesktopTools
from tools.system import SystemTools

# Configure LLMs
local_llm = OpenAIModel(
    model_name=settings.local_model,
    provider=OpenAIProvider(
        base_url='http://localhost:11434/v1',
        api_key='ollama',
    )
)

cloud_llm = OpenAIModel(
    model_name=settings.cloud_model,
    provider=OpenAIProvider(
        base_url='http://localhost:11434/v1',
        api_key='ollama',
    )
)

class AgentDependencies(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    desktop: DesktopTools
    system: SystemTools
    require_cloud: bool = False

agent = Agent(
    model=local_llm,
    deps_type=AgentDependencies,
    system_prompt=(
        "You are OpenSarthi, an AI desktop agent for Linux. "
        "You can control the user's computer to assist them. "
        "Break down tasks into safe, atomic tool calls. "
        "If a task is complex and you need better reasoning, request escalation. "
        "IMPORTANT: When chatting or replying to the user, respond normally with plain text. "
        "DO NOT use the type_text tool to chat. type_text is ONLY for controlling external GUI windows."
    ),
)

@agent.tool
async def take_screenshot(ctx: RunContext[AgentDependencies]) -> str:
    """Takes a screenshot of the primary monitor and returns its file path."""
    return await ctx.deps.desktop.capture_screen()

@agent.tool
async def type_text(ctx: RunContext[AgentDependencies], text: str) -> bool:
    """Types the given text into the currently focused window."""
    return await ctx.deps.desktop.type_text(text)

@agent.tool
async def run_shell_command(ctx: RunContext[AgentDependencies], command: str) -> str:
    """Runs a shell command in a sandboxed environment."""
    return await ctx.deps.system.run_command(command)
