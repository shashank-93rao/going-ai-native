# Writer brief (common to all module writers)

You are writing ONE module of the course "going-ai-native" at the root of this repository.

Before writing, read these in full:
1. STYLE.md: the binding authoring guide (layout, templates, code rules, honesty rules).
2. research/02-final-topics.md: find your module's row. That row is your scope.
3. research/01-gap-analysis.md: the course's stance on each controversy.
4. shared/ainative_kit/llm.py and tracing.py: the client and tracer all code must use.
5. The research notes relevant to your module: research/anthropic.md, openai-karpathy.md, practitioners.md, curricula.md. Grep them for your topics, and read the matching entries, the "Best concrete examples to reuse" sections, and the loop synthesis where relevant.

Then write your module folder (you own ONLY that folder; do not edit anything else).
You may use WebFetch/WebSearch (load via ToolSearch "select:WebFetch,WebSearch") to verify facts or to fill gaps. Prefer primary sources.

Quality bar:
- The reader is an experienced distributed-systems engineer. Be deep, precise, and practical.
- Every concept file has a worked example with real artifacts.
- The code runs, and `.venv/bin/python -m pytest -q <your-module>/code` passes offline. Run it, and fix any failures before finishing.
- Cross-link other modules by their directory names (listed in STYLE.md) where useful. They may not exist yet; links are fine anyway.
- Do not fabricate quotes, numbers, or URLs. Unverified items get hedged or dropped.

When done, reply with:
- the files created
- the test result line
- 3–5 bullets on notable content
- anything you could not verify
