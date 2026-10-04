"""Synthetic evidence-grounded decisions with independent factual quote gates.

Grounding checks authenticate quoted spans and IDs, not the quality of an
inference or decision. Open-ended quality needs separately calibrated judges;
these checks must never be reported as full decision correctness.
"""

import json
import random
from dataclasses import dataclass

from dialectica.json_repair import strip_code_fence


@dataclass(frozen=True)
class EvidenceTask:
    task_id: str
    question: str
    sources: dict[str, str]

    @property
    def statement(self) -> str:
        cards = "\n".join(
            f"[{identifier}] {text}" for identifier, text in self.sources.items()
        )
        return (
            "This is a synthetic decision scenario. Use only the supplied evidence "
            "for factual assertions; label additional premises as assumptions.\n"
            f"QUESTION:\n{self.question}\nEVIDENCE:\n{cards}\n"
            "Commit to one binding decision, give a measurable trigger for changing "
            "it, defend the strongest competing option under the condition where "
            "it would win, and state the main risk. Do not invent factual numbers. "
            "Use 150-350 words total. Return one JSON object only with decision "
            "(string), trigger (string), claims (1-3 objects each containing source_id, "
            "quote copied verbatim from that card, and inference), risks (nonempty "
            "list of strings) and assumptions (list of strings, possibly empty). "
            "A quote is evidence, not proof that your inference follows."
        )

    def verify_content(self, answer: str) -> tuple[bool, str]:
        try:
            payload = json.loads(strip_code_fence(answer))
        except (ValueError, TypeError):
            return False, "Return the required JSON decision object."
        if not isinstance(payload, dict) or any(
            not isinstance(payload.get(key), str) or not payload[key].strip()
            for key in ("decision", "trigger")
        ):
            return False, "decision and trigger must be nonempty strings."
        claims = payload.get("claims")
        if not isinstance(claims, list) or not 1 <= len(claims) <= 3:
            return False, "Supply 1-3 evidence claims."
        for claim in claims:
            if not isinstance(claim, dict):
                return False, "Each claim must be a source/quote/inference object."
            identifier, quote, inference = (
                claim.get(key) for key in ("source_id", "quote", "inference")
            )
            if not isinstance(identifier, str) or identifier not in self.sources:
                return False, "Unknown evidence source."
            if (
                not isinstance(quote, str)
                or len(quote.strip()) < 8
                or quote not in self.sources[identifier]
            ):
                return False, "The quoted evidence does not match its source card."
            if not isinstance(inference, str) or not inference.strip():
                return False, "Each evidence claim requires an explicit inference."
        for key in ("risks", "assumptions"):
            values = payload.get(key)
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                return False, "risks and assumptions must be lists of nonempty strings."
        if not payload["risks"]:
            return False, "At least one risk is required."
        return True, ""


def make_evidence_tasks(split: str, count: int = 8) -> list[EvidenceTask]:
    if split not in {"dev", "heldout"} or count < 1:
        raise ValueError("valid split and positive count required")
    rng = random.Random(61004 if split == "dev" else 101004)
    tasks = []
    for index in range(count):
        case_id = f"evidence-{split}-{index:03}"
        budget, people, weeks = (
            rng.randint(70, 150),
            rng.randint(3, 8),
            rng.randint(6, 12),
        )
        if index % 3 == 0:
            question = "Should the team ship the new feature now, run a limited pilot, or stabilize the existing service first?"
            sources = {
                "S1": f"Case {case_id}. The team has {people} engineers and {weeks} weeks until renewal. The authorized quarter budget is {budget} thousand dollars.",
                "S2": f"The current service had {rng.randint(3, 8)} severe incidents last month. Two were caused by release changes. Customers require incident-free operation during the final two weeks before renewal.",
                "S3": f"A full feature launch costs {budget - 10} thousand dollars and occupies all engineers for {weeks - 1} weeks. A scoped pilot costs {budget // 3} thousand dollars and occupies two engineers for three weeks; demand estimates are unvalidated.",
                "S4": "One renewing customer explicitly values the feature, but the largest customer prioritizes reliability. Stabilization requires three engineers for four weeks and does not demonstrate feature demand.",
            }
        elif index % 3 == 1:
            question = "Choose a hosted vendor, build internally, or run a reversible evaluation for the new data workflow."
            sources = {
                "S1": f"Case {case_id}. The team has {people} engineers, a {weeks}-week deadline and {budget} thousand dollars of committed funding.",
                "S2": "The workflow contains sensitive customer records. Procurement prohibits unapproved cross-region storage. Vendor security approval has not been granted.",
                "S3": f"The hosted offer costs {budget // 2} thousand dollars annually and promises two-week deployment. Its published latency is a vendor claim, not a measured result on this workload.",
                "S4": f"An internal build is estimated at {budget - 5} thousand dollars and {weeks + 2} weeks. A synthetic-data vendor evaluation costs {budget // 8} thousand dollars and two weeks; it provides no evidence of production security compliance.",
            }
        else:
            question = "Decide whether to hire a permanent specialist, use a short contract, or defer expansion while validating demand."
            sources = {
                "S1": f"Case {case_id}. The company has {budget} thousand dollars earmarked for expansion and {weeks} months of cash runway at current burn. The team has {people} engineers.",
                "S2": "Sales pipeline figures are unsigned prospects. Existing customers report slow integrations, but no prospect has committed to paying for the proposed new capability.",
                "S3": f"A permanent hire costs {budget - 10} thousand dollars over six months and takes eight weeks to recruit. A three-month contract costs {budget // 3} thousand dollars and can start in two weeks.",
                "S4": "The specialist would reduce integration delays; a permanent hire retains knowledge. A contract is reversible but creates handover risk. A demand-validation pilot needs one current engineer for four weeks.",
            }
        tasks.append(EvidenceTask(case_id, question, sources))
    return tasks
