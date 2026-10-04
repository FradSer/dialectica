"""Per-arm cost receipts for live experiments; metadata gaps stay explicit.

Install the observer once around a concurrent experiment, then measure each
arm separately. All calls made by that arm, including controller/verifier
calls, are metered. Judging outside the arm is a separate measurement expense.
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields
from time import perf_counter
from typing import Any

from dialectica import agent_runtime
from dialectica.agent_runtime import TokenUsage


@dataclass
class ArmReceipt:
    name: str
    output: Any = None
    error: str | None = None
    calls: int = 0
    failures: int = 0
    seconds: float = 0
    usage: TokenUsage = field(default_factory=TokenUsage)
    records: list[dict[str, Any]] = field(default_factory=list)
    _active: bool = field(default=True, init=False, repr=False)
    _tasks: set[asyncio.Task] = field(default_factory=set, init=False, repr=False)

    def record(self, usage: TokenUsage) -> None:
        self.usage = TokenUsage(
            **{
                f.name: getattr(self.usage, f.name) + getattr(usage, f.name)
                for f in fields(TokenUsage)
            }
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            f.name: asdict(self.usage)
            if f.name == "usage"
            else deepcopy(getattr(self, f.name))
            for f in fields(self)
            if not f.name.startswith("_")
        }


_meter: ContextVar[ArmReceipt | None] = ContextVar("dialectica_eval_arm", default=None)
_observing: bool = False


@contextmanager
def observe_runtime() -> Iterator[None]:
    """One observer per process; task-local counters isolate concurrent arms."""
    global _observing
    if _observing:
        raise RuntimeError("runtime measurement observer is already installed")
    original = agent_runtime.run_agent

    async def observed(agent, instruction: str, **kwargs) -> str:
        meter = _meter.get()
        if meter is not None:
            if not meter._active:
                raise RuntimeError(
                    "measurement arm has finished; await its child tasks"
                )
            meter.calls += 1
            task = asyncio.current_task()
            meter._tasks.add(task)
            model = getattr(agent, "model", None)
            model_name = (
                model if isinstance(model, str) else getattr(model, "model", None)
            )
            system_instruction = getattr(agent, "instruction", None)
            record = {
                "label": getattr(agent, "name", None),
                "model": model_name if isinstance(model_name, str) else None,
                "prompt": instruction,
                "system_instruction": system_instruction
                if isinstance(system_instruction, str)
                else None,
                "raw_output": None,
                "error": None,
                "usage": None,
                "seconds": None,
            }
            meter.records.append(record)
            call_started = perf_counter()
        try:
            try:
                response = await original(agent, instruction, **kwargs)
            except BaseException as error:
                if meter is not None:
                    meter.failures += 1
                    usage = getattr(
                        error, "dialectica_usage", TokenUsage(unknown_calls=1)
                    )
                    meter.record(usage)
                    record["usage"] = asdict(usage)
                    record["error"] = type(error).__name__
                raise
            if meter is not None:
                usage = getattr(response, "usage", TokenUsage(unknown_calls=1))
                meter.record(usage)
                record["usage"] = asdict(usage)
                record["raw_output"] = str(response)
            return response
        finally:
            if meter is not None:
                record["seconds"] = perf_counter() - call_started
                meter._tasks.discard(task)

    _observing = True
    agent_runtime.run_agent = observed
    try:
        yield
    finally:
        agent_runtime.run_agent = original
        _observing = False


async def measure_arm(name: str, run: Callable[[], Awaitable[Any]]) -> ArmReceipt:
    """Measure one arm; errors are explicit receipts, cancellation propagates."""
    receipt = ArmReceipt(name=name)
    token = _meter.set(receipt)
    started = perf_counter()
    try:
        receipt.output = await run()
    except Exception as error:
        receipt.error = type(error).__name__
    finally:
        # Stop inherited contexts from starting more calls during cancellation.
        # Already-running calls still record their final usage before we return.
        receipt._active = False
        try:
            if receipt._tasks:
                receipt.error = "UnjoinedArmCalls"
                receipt.output = None
                pending = list(receipt._tasks)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
        finally:
            receipt.seconds = perf_counter() - started
            _meter.reset(token)
    return receipt
