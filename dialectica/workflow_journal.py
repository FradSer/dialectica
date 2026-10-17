"""Resume/journaling for Workflow runs — cache agent() calls for replay."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sys
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .agent_runtime import TokenUsage

_MAX_ITEM_CAP = 4096
_MAX_AGENT_CALLS = 1000


def default_journal_dir() -> Path:
    base = os.environ.get("DIALECTICA_WORKFLOW_JOURNAL_DIR", ".dialectica/workflows")
    return Path(base)


CONTRACT_VERSION = 2


def _digest(value: Any) -> str:
    # No repr fallback: object identities and opaque state cannot authorize reuse.
    payload = json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def callable_fingerprint(func: Any) -> str:
    import inspect

    from google.adk.tools import FunctionTool

    if isinstance(func, FunctionTool):
        func = func.func
    if inspect.ismethod(func):
        func = func.__func__
    if not inspect.isfunction(func):
        raise ValueError("opaque callable requires recomputation")
    source = inspect.getsource(func)
    file = inspect.getsourcefile(func)
    if file is None:
        raise ValueError("callable source unavailable")
    return _digest(
        [
            func.__module__,
            func.__qualname__,
            source,
            hashlib.sha256(Path(file).read_bytes()).hexdigest(),
        ]
    )


def script_fingerprint(script: Any, *, registry_name: str | None = None) -> str:
    try:
        runtime = [
            (p.name, hashlib.sha256(p.read_bytes()).hexdigest())
            for p in sorted(Path(__file__).parent.glob("*.py"))
        ]
        versions = {
            name: importlib.metadata.version(name)
            for name in ("google-adk", "litellm", "pydantic")
        }
        return _digest(
            [
                CONTRACT_VERSION,
                registry_name,
                callable_fingerprint(script),
                runtime,
                list(sys.version_info[:3]),
                versions,
            ]
        )
    except (TypeError, ValueError, OSError):
        return uuid.uuid4().hex  # unverifiable code never hits a prior cache


def _strict_json_input(value: Any) -> None:
    if type(value) in (str, int, float, bool, type(None)):
        return
    if type(value) is list:
        for item in value:
            _strict_json_input(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _strict_json_input(item)
        return
    raise ValueError("resume args must be strict JSON values")


def args_fingerprint(args: Any) -> str:
    try:
        _strict_json_input(args)
        return _digest(args)
    except (TypeError, ValueError, RecursionError):
        return uuid.uuid4().hex


def schema_fingerprint(schema: type[BaseModel] | None) -> Any:
    if schema is None:
        return None
    import inspect

    file = inspect.getsourcefile(schema)
    if file is None:
        raise ValueError("schema implementation unavailable")
    decorators = schema.__pydantic_decorators__
    validators = []
    for group in (
        decorators.validators,
        decorators.field_validators,
        decorators.root_validators,
        decorators.model_validators,
        decorators.field_serializers,
        decorators.model_serializers,
    ):
        validators.extend(callable_fingerprint(value.func) for value in group.values())
    return [
        schema.model_json_schema(),
        hashlib.sha256(Path(file).read_bytes()).hexdigest(),
        validators,
    ]


def agent_cache_key(
    prompt: str,
    *,
    schema: type[BaseModel] | None,
    tools: list[Any] | None,
    instructions: str,
    label: str | None,
    phase: str | None,
    model: Any,
    isolation: str | None,
    agent_type: str | None,
    sees: list[str] | None = None,
    replay_version: str | None = None,
    max_attempts: int = 3,
) -> str:
    from .tool_policy import capability

    try:
        tool_keys = []
        for tool in tools or ():
            declaration = capability(tool)
            if declaration is None:
                raise ValueError("unversioned tool")
            tool_keys.append([callable_fingerprint(tool), asdict(declaration)])
        if not isinstance(model, (str, type(None))):
            # LiteLlm configuration includes model, endpoint and generation options.
            model = model.model_dump(mode="json")
        return _digest(
            [
                CONTRACT_VERSION,
                prompt,
                schema_fingerprint(schema),
                tool_keys,
                instructions,
                label,
                phase,
                model,
                isolation,
                agent_type,
                sees,
                replay_version,
                max_attempts,
            ]
        )
    except (TypeError, ValueError, OSError, AttributeError):
        return uuid.uuid4().hex


def _atomic_write(path: Path, text: str) -> None:
    import tempfile

    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".journal-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@dataclass
class AgentJournalEntry:
    sequence: int
    cache_key: str
    prompt: str
    result_kind: str  # text | schema | none | error | pending
    result_text: str | None = None
    schema_name: str | None = None
    usage: TokenUsage = field(default_factory=TokenUsage)

    def to_json(self) -> str:
        data = asdict(self)
        data["usage"] = asdict(self.usage)
        return json.dumps(data)

    @classmethod
    def from_json(cls, line: str) -> AgentJournalEntry:
        data = json.loads(line)
        usage = TokenUsage(**data.pop("usage"))
        return cls(usage=usage, **data)


@dataclass
class RunJournal:
    run_id: str
    script_fingerprint: str
    args_fingerprint: str
    entries: list[AgentJournalEntry] = field(default_factory=list)
    effectful_sequences: set[int] = field(default_factory=set)
    resuming: bool = False
    terminal_state: str = "running"
    _live_from: int | None = field(default=None, repr=False)

    def invalidate_from(self, sequence: int) -> None:
        self._live_from = (
            sequence if self._live_from is None else min(self._live_from, sequence)
        )
        self.entries = [e for e in self.entries if e.sequence < sequence]

    def lookup(self, sequence: int, cache_key: str) -> AgentJournalEntry | None:
        if self._live_from is not None and sequence >= self._live_from:
            return None
        entry = next((e for e in self.entries if e.sequence == sequence), None)
        if entry is None:
            self.invalidate_from(sequence)
            return None
        if entry.result_kind not in ("text", "schema") or entry.cache_key != cache_key:
            self.invalidate_from(sequence)
            return None
        return entry

    def append(self, entry: AgentJournalEntry) -> None:
        self.entries = [e for e in self.entries if e.sequence != entry.sequence]
        self.entries.append(entry)
        self.entries.sort(key=lambda e: e.sequence)

    def record_usage(
        self, path: Path, sequence: int, usage: TokenUsage, *, failed: bool
    ) -> None:
        """Keep billing receipts even when resume replaces a failed cache entry."""
        path.parent.mkdir(parents=True, exist_ok=True)
        receipt = {"sequence": sequence, "failed": failed, "usage": asdict(usage)}
        with path.with_name("usage.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(receipt) + "\n")

    def persist(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        # One atomic snapshot is authoritative; a killed writer leaves the old one.
        snapshot = {
            "contract_version": CONTRACT_VERSION,
            "run_id": self.run_id,
            "script_fingerprint": self.script_fingerprint,
            "args_fingerprint": self.args_fingerprint,
            "effectful_sequences": sorted(self.effectful_sequences),
            "terminal_state": self.terminal_state,
            "entries": [json.loads(e.to_json()) for e in self.entries],
        }
        _atomic_write(path, json.dumps(snapshot, indent=2))

    @classmethod
    def load(cls, run_id: str, journal_dir: Path | None = None) -> RunJournal:
        if Path(run_id).name != run_id or run_id in (".", ".."):
            raise ValueError("run_id must be a single directory name")
        root = (journal_dir or default_journal_dir()) / run_id
        path = root / "journal.jsonl"
        try:
            snapshot = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError) as error:
            raise ValueError(
                "legacy or damaged journal cannot safely resume"
            ) from error
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("contract_version") != CONTRACT_VERSION
        ):
            raise ValueError("unsupported resume contract version")
        if snapshot.get("run_id") != run_id:
            raise ValueError("journal run identity does not match its directory")
        entries = [
            AgentJournalEntry.from_json(json.dumps(e)) for e in snapshot["entries"]
        ]
        journal = cls(
            run_id=snapshot["run_id"],
            script_fingerprint=snapshot["script_fingerprint"],
            args_fingerprint=snapshot["args_fingerprint"],
            entries=entries,
            effectful_sequences=set(snapshot["effectful_sequences"]),
            resuming=True,
            terminal_state=snapshot.get("terminal_state", "unknown"),
        )
        if len({e.sequence for e in entries}) != len(entries):
            journal.entries.clear()
            journal._live_from = 0
        return journal

    @classmethod
    def create(
        cls,
        *,
        script: Any,
        args: Any,
        registry_name: str | None = None,
        resume_run_id: str | None = None,
        journal_dir: Path | None = None,
        resume_version: str | None = None,
    ) -> tuple[RunJournal, Path]:
        root = journal_dir or default_journal_dir()
        fp_script = (
            _digest(
                [
                    resume_version,
                    script_fingerprint(script, registry_name=registry_name),
                ]
            )
            if resume_version
            else uuid.uuid4().hex
        )
        fp_args = args_fingerprint(args)
        if resume_run_id:
            journal = cls.load(resume_run_id, root)
            if (
                journal.script_fingerprint != fp_script
                or journal.args_fingerprint != fp_args
            ):
                journal._live_from = 0
                journal.entries.clear()
                journal.script_fingerprint = fp_script
                journal.args_fingerprint = fp_args
            return journal, root / journal.run_id / "journal.jsonl"
        run_id = str(uuid.uuid4())
        journal = cls(
            run_id=run_id,
            script_fingerprint=fp_script,
            args_fingerprint=fp_args,
        )
        return journal, root / run_id / "journal.jsonl"


def serialize_agent_result(
    result: Any, schema: type[BaseModel] | None
) -> AgentJournalEntry:
    if result is None:
        return AgentJournalEntry(
            sequence=-1,
            cache_key="",
            prompt="",
            result_kind="none",
        )
    if schema is not None and isinstance(result, BaseModel):
        return AgentJournalEntry(
            sequence=-1,
            cache_key="",
            prompt="",
            result_kind="schema",
            result_text=result.model_dump_json(),
            schema_name=schema.__name__,
        )
    return AgentJournalEntry(
        sequence=-1,
        cache_key="",
        prompt="",
        result_kind="text",
        result_text=str(result),
    )


def deserialize_agent_result(
    entry: AgentJournalEntry, schema: type[BaseModel] | None
) -> Any:
    if entry.result_kind == "none":
        return None
    if entry.result_kind == "schema" and schema is not None:
        return schema.model_validate_json(entry.result_text or "{}")
    return entry.result_text


class JournalBusyError(RuntimeError):
    """Another process is already resuming this run."""


@contextmanager
def journal_lock(root: Path):
    """OS lock releases on process death; lock files themselves may remain."""
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            stream.write(b"0")
            stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise JournalBusyError("run is already active") from error
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise JournalBusyError("run is already active") from error
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)
