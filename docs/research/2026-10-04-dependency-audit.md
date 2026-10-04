# Dependency audit while the held-out environment is frozen

This is a read-only check, not a completion claim for dependency upgrades.
`uv pip list --outdated --format json` queried the configured package index on
2026-10-04. Installed distribution metadata was then inspected with
`importlib.metadata` and `packaging.Requirement`. No environment, manifest or
lockfile was modified during the running campaign.

The query returned ten outdated distributions. Eight latest releases are excluded
by active requirements of currently installed upstream packages:

| Package | Installed | Index latest | Active upstream constraint |
|---|---|---|---|
| huggingface-hub | 1.33.0 | 2.1.1 | tokenizers requires `<2.0` |
| importlib-metadata | 8.9.0 | 9.0.1 | litellm requires `<9.0` |
| multidict | 6.9.1 | 7.0.0 | aiohttp requires `<7.0` |
| openai | 2.54.0 | 3.24.0 | litellm requires `<3.0.0` |
| opentelemetry-api | 1.42.1 | 1.45.0 | google-adk requires `<=1.42.1`; SDK/conventions also pin it |
| opentelemetry-sdk | 1.42.1 | 1.45.0 | google-adk requires `<=1.42.1` |
| pydantic-core | 2.46.5 | 2.49.0 | pydantic requires `==2.46.5` |
| websockets | 15.0.1 | 17.2 | google-adk requires `<16`; google-genai requires `<17.0` |

Inactive extra requirements were not treated as constraints on the default
environment. In particular, ADK's optional OpenAI extra is unnecessary to explain
the installed OpenAI ceiling: LiteLLM's active requirement already excludes v3.
These constraints are evidence from installed versions, not proof that a future
upstream release cannot remove them. The package-index query found no newer
release for the installed ADK, LiteLLM, Pydantic or tokenizers distributions.

Two latest versions have no excluding requirement in the installed metadata:
FastAPI 0.141.1 → 0.142.2 and zipp 4.1.0 → 4.1.1. Installed metadata alone does
not establish compatibility: a newer release can introduce a conflicting
requirement. Follow-up checked
[FastAPI 0.142.2 metadata](https://pypi.org/pypi/fastapi/0.142.2/json), which
requires `opentelemetry-api>=1.44.0`, incompatible with ADK's `<=1.42.1`.
`uv lock --upgrade --dry-run` resolved all 94 packages and proposed only
zipp 4.1.0 → 4.1.1. Nine newer distributions are therefore currently excluded;
only zipp remains a compatible pending upgrade. The dry run did not write the
lockfile or alter the installed environment.

After the frozen campaign reaches a
terminal state, refresh the index and upgrade the complete lockfile with `uv`,
without overriding maintained upstream constraints. Then run affected/full checks
and real-model E2E in the new environment. Do not silently change the environment
of the already declared experiment, or claim that latest-index versions were all
installed by this audit.

## Final upgrade after campaign completion

After all seven terminal receipts were verified and the campaign exited zero,
`uv lock --upgrade` refreshed the complete resolution: 94 packages resolved;
only zipp changed, from 4.1.0 to 4.1.1. `uv run` installed 4.1.1. Maintained
upstream constraints were preserved; absolute-latest incompatible transitive
versions were not forced. The frozen source archive retains the experiment's
original lockfile, so final-environment validation is separate evidence.

Final environment: 212 offline tests passed (9 live tests deselected); Ruff,
formatting (97 Python files), wheel/source package build and diff whitespace
checks passed. Final real-model E2E is recorded separately in
`results/2026-10-04-final-live-e2e-gemini-gpt.txt`: 9 passed, zero skipped,
114.77 seconds. The first unavailable historical-roster attempt (8 pass / 1 fail)
is retained at `results/2026-10-04-final-live-e2e.txt`. One upstream Pydantic
`ReadOnly` warning remains; it does not establish hidden provider billing.
