---
description: Run the full daily Honda Accord watch (all nine agents) and refresh the ranked list.
---
Run today's accord-watch pipeline exactly as described in CLAUDE.md.
Before each stage, print one line so the person watching can follow along, e.g. "▶ الكشّاف (scout) بدأ" and after it "✓ الكشّاف (scout): 45 إعلان، 3 جديدة". Keep a task list with one item per agent and tick each off as it finishes.
Listings already saved today are skipped by the stage checks, so a run that was stopped halfway simply continues.

1. `python tools/db.py init`
2. Use the **scout** subagent.
3. Use the **archivist** subagent.
4. Use the **text-auditor** and **visual-inspector** subagents in parallel.
5. Use the **cross-checker** subagent.
6. Use the **inferencer** subagent, then the **pricer** subagent.
7. Use the **ranker** subagent.
8. Use the **reporter** subagent.

If a stage fails, record what failed, continue with the stages that can still run, and mention it in the final digest.
Finish with the Reporter's Arabic highlights and the path `reports/latest.html`.
