"""Problems that structurally reward a multi-angle gather->stress-test->synthesize
workflow over a single linear pass: genuine multi-stakeholder tension, opposing
correctness criteria, and no single right answer a one-shot can commit to.

A single call tends to commit to one side and hand-wave the tension; the workflow
forces parallel opposing perspectives, adversarial critique, and an explicit
synthesis that resolves the tension — the one shape a single forward pass cannot
hold in working memory at once.
"""

from evals.problems import EvalProblem

META_PROBLEMS = [
    EvalProblem(
        id="remote-rtc",
        statement=(
            "A 2000-person company must decide its remote-work policy for next "
            "year. Engineering (mostly senior, distributed across 6 timezones) "
            "wants full remote; Sales (client-facing, in 3 hub cities) wants "
            "3-days-in-office; HR cites retention data favoring flexibility; "
            "Finance models show $12M/yr in real-estate savings from full remote "
            "but $4M in lost cross-team collaboration (their estimate, disputed). "
            "Recommend ONE policy. The recommendation is wrong if it just "
            "compromises to 'hybrid, 2 days in office' without resolving which "
            "stakeholder's constraint is actually binding."
        ),
    ),
    EvalProblem(
        id="ai-hiring-triage",
        statement=(
            "A mid-size tech company is deciding whether to use an AI resume "
            "screener that the vendor claims reduces screening time by 70% with "
            "no accuracy loss. The legal team flagged disparate-impact risk; "
            "engineering wants to ship fast; HR's audit found the vendor's "
            "validation set had a demographic skew the vendor did not disclose. "
            "Recommend whether to deploy, conditionally deploy, or reject — and "
            "name the specific disconfirmation: what evidence, if it appeared in "
            "the first 90 days, would force reversing the decision?"
        ),
    ),
    EvalProblem(
        id="monolith-breakup",
        statement=(
            "A 12-year-old monolith (2M LOC, 40 engineers) is blocking "
            "deployment velocity. Platform team proposes a 2-year migration to "
            "microservices; the staff engineers who built the monolith argue "
            "strangler-fig incremental extraction is lower-risk and the platform "
            "team's plan underestimates distributed-systems complexity by 3x. "
            "Both are partly right. Recommend the migration strategy and the "
            "precise decision rule for when to extract the next service vs stop."
        ),
    ),
    EvalProblem(
        id="pricing-tier-split",
        statement=(
            "A B2B SaaS at $50/user/month with 800 customers is losing mid-market "
            "deals (competitor at $25). Sales wants a cheaper tier; Product fears "
            "cannibalization of the $50 tier; Finance models show the $25 tier "
            "is profitable only if <15% of existing customers downgrade. Recommend "
            "the pricing change AND the concrete downgrade-rate tripwire that, "
            "if exceeded in Q1, kills the new tier."
        ),
    ),
    EvalProblem(
        id="incident-blameless",
        statement=(
            "After a 6-hour outage, the VP wants the on-call engineer fired "
            "(they pushed the deploy that triggered it). The postmortem shows "
            "3 prior latent bugs + a missing canary + a runbook gap, none of "
            "which the on-call owned. Engineering culture wants blameless "
            "postmortems; the VP wants accountability. Recommend the response — "
            "and resolve the tension: under what specific condition WOULD "
            "firing the on-call be the correct call (vs this case)?"
        ),
    ),
]
