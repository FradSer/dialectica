"""Host-declared tool capabilities, enforced before tools reach ADK.

Declarations are trusted host configuration, not a security sandbox. A read tool
must itself restrict paths, commands and remote capabilities appropriately.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, TypeVar

T = TypeVar("T", bound=Callable)


@dataclass(frozen=True)
class ToolCapability:
    access: Literal["read", "write"]
    version: str


def tool_capability(*, access: Literal["read", "write"], version: str):
    """Declare a callable's authority and host-managed dependency version.

    Apply to the function before wrapping it in an ADK FunctionTool. Bump version
    for dependencies/configuration not captured by the callable's source file.
    """
    if access not in ("read", "write") or not version.strip():
        raise ValueError("tool capability requires read/write access and a version")

    def decorate(func: T) -> T:
        vars(func)["__dialectica_capability__"] = ToolCapability(access, version)
        return func

    return decorate


def capability(tool: Any) -> ToolCapability | None:
    # Only unwrap ADK's known FunctionTool, never arbitrary toolset expansion.
    import inspect

    from google.adk.tools import FunctionTool

    func = tool.func if isinstance(tool, FunctionTool) else tool
    if not inspect.isfunction(func):
        return None
    value = getattr(func, "__dialectica_capability__", None)
    return value if isinstance(value, ToolCapability) else None


def enforce_tools(tools: list[Any], agent_type: str | None) -> list[Any]:
    if agent_type == "Explore":
        for tool in tools:
            declaration = capability(tool)
            if declaration is None or declaration.access != "read":
                raise PermissionError(
                    "Explore requires every tool to declare read capability; "
                    "unclassified, write and expandable toolsets are refused"
                )
    return tools
