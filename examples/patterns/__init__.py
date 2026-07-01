"""Reference implementations of demoted engines, expressed as ``Workflow`` scripts.

Agentic, dialectic, ensemble, and ToT+GAN were each measured (see README
"Evaluation") to either tie/lose a prompt-matched single call as pure-LLM
scaffolds, or — for agentic — to need nothing beyond ``workflow.agent(tools=...)``,
already a first-class primitive. None of them earn a place in the shipped
public API (``dialectica.__all__`` is now just the ``Workflow`` kernel plus
``create_repair_engine``). These scripts are kept as runnable, honest
reference code — not shipped in the wheel, same as ``evals/``.
"""
