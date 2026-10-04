# Development Study: Oracle-Free Selection Over Self-Refinement Trajectories

**Date:** 2026-10-04  
**Split:** `dev` (seeds: 51004 / dev portfolio tasks)  
**Model:** `openai:gemini-3.5-flash-lite` (via cliproxy)  
**Configuration:** 8 tasks × 2 repeats = 16 trials; 8 steps per self-refinement trajectory; budget allowance 8 workflow steps.  
**Raw Artifacts:** [`results/2026-10-04-selection-dev-v1.json`](results/2026-10-04-selection-dev-v1.json), [`results/2026-10-04-selection-dev-v1.protocol.json`](results/2026-10-04-selection-dev-v1.protocol.json)

---

## 1. Motivation & Context

In the held-out campaign ([`2026-10-04-heldout-selection-diagnostics.md`](2026-10-04-heldout-selection-diagnostics.md)), a striking asymmetry was observed:
- `meta-gemini-budget12 / self_refine`: 21/24 trials generated at least one globally optimal candidate during the 12 steps, but final answers passed only 8/24 (13 covered trials were lost).
- `meta-gemini-budget6 / self_refine`: 19/24 trials generated an optimal candidate, but final answers passed only 10/24 (9 lost).

The standard self-refinement recipe defaults to returning the final step (`last`). However, an unguided LLM reflecting on its own output frequently wanders away from an optimal solution it already found, drifting into subtle constraint violations or lower-reward subsets.

The held-out diagnostics noted that an *oracle* selector would overstate deployable gains, because a real deployment cannot consult the hidden optimal solution. This study asks:
> **Can deployable, oracle-free selection rules recover correct intermediate answers without privileged access to the hidden optimum?**

---

## 2. Tested Selection Rules

All selection rules evaluate the **exact same saved candidate trajectories** produced during self-refinement:

| Rule | Description | Privileged Info? | Additional Cost |
|---|---|---|---|
| `first` | Single-call baseline (attempt 0). | None | 0 |
| `last` | Standard self-refine output (attempt 7). | None | 0 |
| `plurality` | Mode (most frequent parsed prediction); ties broken by latest occurrence. | None | 0 |
| `convergence` | First answer confirmed by its immediate successor ($k$ where $A_k = A_{k-1}$); fallback to last parseable. | None | 0 (enables early stopping) |
| `checker` | Feasibility verification (capacity + exclusion pairs) and highest total reward calculated directly from problem statement numbers. | None (only prompt data) | 0 |
| `llm_pick` | Prompt-based selector: presents distinct candidates to the LLM to verify and select. | None | 1 workflow step |
| *Coverage (Upper Bound)* | At least one candidate in the trajectory passes the evaluator's hidden oracle. | Evaluator oracle | N/A (upper bound) |

---

## 3. Results (16 Trials)

| Rule / Metric | Passed / 16 | Pass Rate | Rescued vs `last` | Harmed vs `last` | Unparseable / None | Notes |
|---|---:|---:|---:|---:|---:|---|
| **Coverage (Upper bound)** | **9** | **56.25%** | — | — | — | 9 of 16 trajectories contained the optimal solution |
| `first` (single-call) | 2 | 12.5% | 0 | 0 | 0 | Baseline single attempt |
| `last` (self-refine) | 2 | 12.5% | — | — | 0 | **Ties single-call** (reproducing Dialectica finding #2) |
| `plurality` | 4 | 25.0% | +2 | 0 | 0 | Mode over trajectory provides modest stabilization |
| `convergence` | 3 | 18.8% | +1 | 0 | 0 | Mean steps if stopped at convergence: **3.06 steps** (vs 8) |
| **`checker`** | **9** | **56.25%** | **+7** | **0** | **0** | **Captures 100% of available coverage (9/9)!** |
| `llm_pick` | 3 | 18.8% | +1 | 0 | 9 | Suffers from 9 unparseable selections / refusal to choose |

---

## 4. Key Findings

1. **Unguided Self-Refinement Suffers Severe Trajectory Drift:**
   Without an external check, self-refine produced an optimal answer in 9/16 trials, but discarded it by step 7 in 7 of those 9 trials (a **77.8% loss of intermediate successes**). As a result, `last` scored 2/16 (12.5%), exactly tying the single call `first` (2/16).
2. **Local, Oracle-Free Verifiers ("Checker") Completely Close the Gap:**
   The `checker` rule does not know the optimal reward or the hidden oracle. It only checks constraint satisfaction (capacity, exclusions) and sums the rewards from the prompt. By simply tracking the highest-reward feasible candidate seen across the trajectory, it scored **9/16 (56.25%)**, recovering every single lost optimal candidate (**+7 rescues, 0 harmed**).
3. **LLM-as-Selector (`llm_pick`) Fails to Function Reliably:**
   Asking the LLM to inspect its own distinct candidates and choose the best one yielded only 3/16, with 9 failures due to JSON extraction errors or indecision. It fails at the very job the deterministic `checker` does effortlessly.
4. **Early Stopping via Convergence:**
   The `convergence` rule achieved 3/16 passes (beating `last`'s 2/16) while requiring only **3.06 calls on average** rather than 8, saving over 60% of inference tokens when candidates stabilize.

---

## 5. Architectural Implications for Dialectica

These empirical results reinforce Dialectica's foundational design choices:
- **Verifier-in-the-Loop is Mandatory:** A purely verbal self-critique loop cannot reliably hold onto correct ground truth in combinatorial or constraint-heavy tasks.
- **Trajectory Retention in `create_repair_engine`:** Currently, `IterativeRepairEngine` returns the final attempt when attempts are exhausted without a full pass. For tasks with partial verifiers (e.g., feasibility or objective scorers), keeping the **best-valid candidate across the history** rather than the terminal attempt prevents trajectory-drift loss.
