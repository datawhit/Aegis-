"""Prompt templates.

Keeping prompts in a dedicated package gives us one place to version them.
The triage prompt is referenced by `prompt_template_id="triage:v1"` on the
`ai_reasoning_snapshots` table — when we revise the prompt, we bump the
version so the audit chain still tells the truth about how each decision
was made.
"""
