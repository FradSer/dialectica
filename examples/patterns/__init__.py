"""Reference implementations expressed as ``Workflow`` scripts.

Shipped API stays ``Workflow`` + ``create_repair_engine``. This package holds:

- **Canonical open-ended recipe** — ``reflection_pattern``
  (``create_reflection_engine``): hetero gather → frame → critique →
  synthesize. Measured win on meta / meta+default (README findings #6 / #7).
- **Mode ablation switcher** — ``quality_workflow_pattern``
  (``reflection`` / ``adversarial`` / ``dialectic``). Prefer reflection unless
  comparing modes.
- **Demoted engines** — agentic (folded into ``agent(tools=...)``), dialectic,
  ensemble (CUT: scorer adds nothing over heterogeneity), ToT+GAN (dominated).

Not shipped in the wheel, same as ``evals/``. Import like the evals do::

    from examples.patterns.reflection_pattern import create_reflection_engine
"""
