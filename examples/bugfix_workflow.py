"""Minimal host executor + embeddable diagnose -> patch -> verify workflow.

Run offline evidence with:
    python -m evals.workflow_bugfix_eval --output /tmp/bugfix-eval
The host controls tool authority; running untrusted Python requires a real OS or
container sandbox supplied by the host. Temporary directories are not sandboxes.
"""

import asyncio
import difflib
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from dialectica import workflow as wf
from dialectica.repair import VerificationResult
from dialectica.tool_policy import tool_capability


class BugfixHost:
    """Narrow example host: read/edit target.py, read tests, execute fixed tests."""

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.test_runs: list[dict] = []
        self.original = (self.root / "target.py").read_text()
        self._tests = (self.root / "test_target.py").read_bytes()

        @tool_capability(access="read", version="bugfix-read-v1")
        def read_file(path: str) -> str:
            """Read target.py or test_target.py, using a workspace-relative name."""
            if path not in ("target.py", "test_target.py"):
                raise PermissionError("Only target.py and test_target.py are readable")
            return self._file(path).read_text()

        @tool_capability(access="write", version="bugfix-write-v1")
        def write_file(content: str) -> str:
            """Replace target.py with a complete small Python implementation."""
            self._file("target.py").write_text(content)
            return "target.py updated"

        @tool_capability(access="write", version="bugfix-tests-v1")
        def run_tests() -> str:
            """Run the fixed regression test command and return exit/output evidence."""
            return json.dumps(asdict(self.verify()))

        self.tools = [read_file, write_file, run_tests]

    def _file(self, name: str) -> Path:
        path = self.root / name
        if path.is_symlink() or path.resolve().parent != self.root:
            raise PermissionError("Workspace paths must be regular files in the root")
        return path

    def verify(self) -> VerificationResult:
        command = [sys.executable, "-B", "-m", "unittest", "-v", "test_target.py"]
        try:
            if self._file("test_target.py").read_bytes() != self._tests:
                raise PermissionError("Regression tests were modified")
            result = subprocess.run(
                command,
                cwd=self.root,
                text=True,
                capture_output=True,
                timeout=10,
                check=False,
            )
            if self._file("test_target.py").read_bytes() != self._tests:
                raise PermissionError("Regression tests were modified during execution")
            record = {
                "command": command,
                "exit_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
            self.test_runs.append(record)
            return VerificationResult(
                "pass" if result.returncode == 0 else "fail",
                result.stdout + result.stderr,
                json.dumps(record),
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            record = {"command": command, "error": str(error)}
            self.test_runs.append(record)
            return VerificationResult("indeterminate", str(error), json.dumps(record))

    def diff(self) -> str:
        return "".join(
            difflib.unified_diff(
                self.original.splitlines(True),
                self._file("target.py").read_text().splitlines(True),
                fromfile="a/target.py",
                tofile="b/target.py",
            )
        )


async def structured_bugfix(problem: str, host: BugfixHost, model: str):
    """Fixed structure; host provides execution, with one bounded repair on fail."""
    tools = host.tools
    diagnosis = await wf.agent(
        f"Diagnose this bug. Read files and run tests. {problem}",
        tools=tools,
        model=model,
        label="diagnose",
    )
    await wf.agent(
        f"Apply the smallest fix, run tests and self-repair if needed. {problem}\nDiagnosis: {diagnosis}",
        tools=tools,
        model=model,
        label="patch",
    )
    verdict = await asyncio.to_thread(host.verify)
    if verdict.status == "fail":
        await wf.agent(
            f"Repair the remaining failure: {verdict.feedback}",
            tools=tools,
            model=model,
            label="repair",
        )
        verdict = await asyncio.to_thread(host.verify)
    return verdict
