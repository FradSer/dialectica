"""Budgeted artifact orchestration inspired by arXiv:2609.38147, section 3.

Research mode, not a benchmark replication: each controller stage is a single
structured call, workers are text calls, and there are no memory tools or coding
agents. Staged control sees a compact assessment and newly produced artifacts;
direct control sees accumulated artifacts. Both have the same actions/roster.
The artifact graph is returned for persistence by the experiment harness.
"""

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from dialectica import BudgetExhausted
from dialectica import workflow as wf


class Action(BaseModel):
    kind: Literal["run", "stop"]
    artifact_id: str | None = Field(
        default=None,
        description="Only for stop: ID of the stored answer to submit. For run this MUST be null.",
    )
    instruction: str = Field(
        default="",
        description="For run: nonempty worker assignment. For stop: empty string.",
    )
    context_ids: list[str] = Field(
        default_factory=list,
        description="For run: IDs of prior artifacts supplied to worker. For stop: empty list.",
    )
    worker_index: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_action(self) -> "Action":
        if self.kind == "stop":
            if not self.artifact_id or self.instruction or self.context_ids:
                raise ValueError(
                    "stop must select one stored artifact without new work"
                )
        elif self.artifact_id is not None or not self.instruction.strip():
            raise ValueError(
                "run requires an instruction and cannot submit an artifact"
            )
        return self


class Assessment(BaseModel):
    state: str = Field(min_length=1, max_length=4000)


class Proposals(BaseModel):
    options: list[Action] = Field(min_length=1, max_length=4)


class Evaluation(BaseModel):
    option: int = Field(ge=0)
    rationale: str


@dataclass
class MetaReasoningEngine:
    problem: str
    workers: list[str | None]
    controller_model: str | None
    mode: Literal["staged", "direct"]
    max_calls: int

    async def run(self) -> dict[str, Any]:
        async def script() -> dict[str, Any]:
            artifacts: dict[str, dict[str, Any]] = {}
            history = []
            state = ""
            selected_id = "artifact-0"
            forced_stop = True
            calls = 0
            controller_calls = 0
            worker_calls = 0

            def affordable(count: int) -> bool:
                pool = wf.budget()
                return self.max_calls - calls >= count and (
                    pool.remaining() >= count
                    if pool.unit == "calls"
                    else pool.remaining() > 0
                )

            async def call(
                prompt: str,
                model: str | None,
                label: str,
                schema: type[BaseModel] | None = None,
            ) -> Any:
                nonlocal calls, controller_calls, worker_calls
                if not affordable(1):
                    raise BudgetExhausted("artifact orchestration allowance exhausted")
                result = await wf.agent(
                    prompt,
                    model=model,
                    schema=schema,
                    label=label,
                    sees=[],
                    max_attempts=1,
                )
                calls += 1
                if schema is None:
                    worker_calls += 1
                    if not isinstance(result, str) or not result.strip():
                        raise TypeError("invalid worker artifact")
                else:
                    controller_calls += 1
                    if not isinstance(result, schema):
                        raise TypeError("invalid controller response")
                return result

            def validate(action: Action) -> None:
                ids = (
                    action.context_ids if action.kind == "run" else [action.artifact_id]
                )
                if any(identifier not in artifacts for identifier in ids):
                    raise ValueError("unknown artifact reference")
                if action.worker_index >= len(self.workers):
                    raise ValueError("unknown worker index")
                if len(set(action.context_ids)) != len(action.context_ids):
                    raise ValueError("duplicate artifact context")

            async def work(action: Action) -> str:
                validate(action)
                context = [artifacts[identifier] for identifier in action.context_ids]
                answer = await call(
                    f"TASK:\n{self.problem}\nASSIGNMENT:\n{action.instruction}\n"
                    f"SELECTED ARTIFACTS:\n{json.dumps(context)}\n"
                    "Return a complete answer to the task. Follow its required output format.",
                    self.workers[action.worker_index],
                    f"meta-worker-{worker_calls}",
                )
                identifier = f"artifact-{len(artifacts)}"
                artifacts[identifier] = {
                    "id": identifier,
                    "answer": answer,
                    "parents": action.context_ids,
                    "worker_index": action.worker_index,
                    "instruction": action.instruction,
                }
                return identifier

            selected_id = await work(
                Action(kind="run", instruction="Solve the task carefully.")
            )
            new_ids = [selected_id]
            try:
                while affordable(4 if self.mode == "staged" else 1):
                    cycle = len(history)
                    catalog = [
                        {
                            "id": a["id"],
                            "parents": a["parents"],
                            "instruction": a["instruction"],
                        }
                        for a in artifacts.values()
                    ]
                    common = f"TASK:\n{self.problem}\nARTIFACT CATALOG:\n{json.dumps(catalog)}\n"
                    actions = (
                        "Use run to assign one worker, choosing worker_index from "
                        f"0..{len(self.workers) - 1} and existing context_ids. "
                        "Use stop to select an existing answer by artifact_id. "
                        "For run, artifact_id MUST be null; put any input artifact IDs "
                        "in context_ids instead, and give a nonempty instruction. "
                        "For stop, instruction MUST be empty and context_ids MUST be []. "
                        "Never submit a new answer in a stop action."
                    )
                    if self.mode == "direct":
                        action = await call(
                            common
                            + f"STORED WORK:\n{json.dumps(list(artifacts.values()))}\n"
                            + f"Remaining local calls: {self.max_calls - calls}; "
                            + f"outer budget remaining: {wf.budget().remaining()}.\n"
                            + actions,
                            self.controller_model,
                            f"meta-direct-{cycle}",
                            Action,
                        )
                        control = {"action": action.model_dump()}
                    else:
                        assessment = await call(
                            common
                            + f"PRIOR ASSESSMENT:\n{state}\nNEW WORK:\n"
                            + json.dumps([artifacts[i] for i in new_ids])
                            + "\nUpdate a compact assessment of progress and unresolved flaws. "
                            "Assess reliability without claiming objective proof.",
                            self.controller_model,
                            f"meta-assess-{cycle}",
                            Assessment,
                        )
                        state = assessment.state
                        proposals = await call(
                            common
                            + f"ASSESSMENT:\n{state}\nPropose useful alternative computations.\n"
                            + actions,
                            self.controller_model,
                            f"meta-propose-{cycle}",
                            Proposals,
                        )
                        for proposal in proposals.options:
                            validate(proposal)
                        evaluation = await call(
                            common
                            + f"ASSESSMENT:\n{state}\nOPTIONS:\n{proposals.model_dump_json()}\n"
                            + f"Remaining local calls: {self.max_calls - calls}; "
                            + f"outer budget remaining: {wf.budget().remaining()}.\n"
                            + "Select a zero-based option, weighing expected value and total cost; "
                            "dispatch itself consumes another call before any worker can run.",
                            self.controller_model,
                            f"meta-evaluate-{cycle}",
                            Evaluation,
                        )
                        if evaluation.option >= len(proposals.options):
                            raise ValueError("unknown proposal index")
                        proposal = proposals.options[evaluation.option]
                        action = await call(
                            common
                            + f"ASSESSMENT:\n{state}\nCHOSEN PROPOSAL:\n{proposal.model_dump_json()}\n"
                            + "Dispatch this proposal; preserve its kind, worker_index and stop target. "
                            "For run, refine the instruction and select required artifact contexts.\n"
                            + actions,
                            self.controller_model,
                            f"meta-dispatch-{cycle}",
                            Action,
                        )
                        if (
                            action.kind != proposal.kind
                            or action.worker_index != proposal.worker_index
                            or (
                                action.kind == "stop"
                                and action.artifact_id != proposal.artifact_id
                            )
                        ):
                            raise ValueError("dispatch changed the chosen proposal")
                        control = {
                            "assessment": state,
                            "proposals": proposals.model_dump(),
                            "evaluation": evaluation.model_dump(),
                            "action": action.model_dump(),
                        }
                    validate(action)
                    history.append(control)
                    if action.kind == "stop":
                        selected_id = action.artifact_id
                        forced_stop = False
                        control["status"] = "stopped"
                        break
                    if not affordable(1):
                        control["status"] = "skipped_budget"
                        break
                    try:
                        selected_id = await work(action)
                    except BudgetExhausted:
                        control["status"] = "skipped_budget"
                        raise
                    control["status"] = "executed"
                    control["produced_id"] = selected_id
                    new_ids = [selected_id]
            except BudgetExhausted:
                # Token budgets may end mid-cycle. Submit stored work without
                # making an uncharged synthesis call or inventing an artifact.
                pass
            return {
                "final_answer": artifacts[selected_id]["answer"],
                "selected_id": selected_id,
                "forced_stop": forced_stop,
                "artifacts": list(artifacts.values()),
                "history": history,
                "controller_calls": controller_calls,
                "worker_calls": worker_calls,
                "calls": calls,
                "mode": self.mode,
            }

        return await wf.workflow(script)


def create_meta_reasoning_engine(
    problem: str,
    *,
    workers: list[str | None] | None = None,
    controller_model: str | None = None,
    mode: Literal["staged", "direct"] = "staged",
    max_calls: int = 12,
) -> MetaReasoningEngine:
    if max_calls < 1 or mode not in {"staged", "direct"} or workers == []:
        raise ValueError("positive allowance, nonempty roster and valid mode required")
    return MetaReasoningEngine(
        problem, workers or [None], controller_model, mode, max_calls
    )
