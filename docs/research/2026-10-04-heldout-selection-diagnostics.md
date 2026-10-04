# Held-out generation coverage and final selection

These post-hoc descriptive counts are derived from frozen raw rows. They do not change the declared bootstrap analyses, tune held-out mechanisms or establish statistical superiority. Each arm has 24 trials. Coverage means at least one saved candidate/artifact passes the evaluator-only objective verifier; it is an upper bound, not an oracle available to the arm. Failed claim arms have no complete returned candidate set: their coverage is missing, not zero. Reliability denominators still include them.

| Study / arm | Coverage observed | Correct candidate present | Final correct | Correct candidate lost |
|---|---:|---:|---:|---:|
| claims-gemini-k6 / single | 16/24 | 4 | 4 | 0 |
| claims-gemini-k6 / consensus | 20/24 | 13 | 7 | 6 |
| claims-gemini-k6 / self_refine | 19/24 | 12 | 7 | 5 |
| claims-gemini-k6 / claims | 22/24 | 9 | 6 | 3 |
| claims-gemini-k3 / single | 19/24 | 3 | 3 | 0 |
| claims-gemini-k3 / consensus | 21/24 | 9 | 3 | 6 |
| claims-gemini-k3 / self_refine | 23/24 | 12 | 7 | 5 |
| claims-gemini-k3 / claims | 23/24 | 8 | 7 | 1 |
| meta-gemini-budget12 / single | 24/24 | 5 | 5 | 0 |
| meta-gemini-budget12 / consensus | 24/24 | 8 | 3 | 5 |
| meta-gemini-budget12 / self_refine | 24/24 | 21 | 8 | 13 |
| meta-gemini-budget12 / staged | 24/24 | 2 | 2 | 0 |
| meta-gemini-budget12 / direct | 24/24 | 3 | 3 | 0 |
| meta-gemini-budget6 / single | 24/24 | 5 | 5 | 0 |
| meta-gemini-budget6 / consensus | 24/24 | 6 | 4 | 2 |
| meta-gemini-budget6 / self_refine | 24/24 | 19 | 10 | 9 |
| meta-gemini-budget6 / staged | 24/24 | 4 | 4 | 0 |
| meta-gemini-budget6 / direct | 24/24 | 0 | 0 | 0 |

Claim weighting rescued zero and harmed zero trials against unweighted consensus on exactly the same returned candidates: K=6 has 22 observed trials (6 correct with either rule); K=3 has 23 (7 correct with either rule). This is no measured selection benefit in these observations, not an equivalence proof. The remaining 2/1 failed claim trials have incomplete coverage.

Staged/direct controllers have no selection loss in the completed meta studies: their low final scores coincide with low candidate coverage (2/3 at budget 12 and 4/0 at budget 6). This points to candidate generation/control allocation, rather than a demonstrated selection-only bottleneck. It does not isolate a causal component.

Self-refinement produces correct intermediate answers in 21/24 trials at budget 12 and 19/24 at budget 6, but final answers pass only 8/24 and 10/24. Last-answer selection loses 13 and 9 covered trials respectively. Consensus similarly loses 5 and 2. An oracle selector would overstate deployable gains; these diagnostics motivate future development experiments, not retuning on this held-out pool.

Claim and meta output contracts differ, as do realized token costs. Do not pool their scores or present nominal workflow allowances as matched tokens/dollars. Strong single controls remain observed ceilings on the same task pool, not mechanism tests on that stronger model.
