---
name: jev-marketing-decisions
description: Use when a marketer wants to sort, route, classify, score or tag marketing records in bulk with TypeSafe's Jev model (inbound leads, outbound replies, content drafts, asset libraries), or wants help designing Jev questions and confidence thresholds for a marketing workflow.
---

# Jev for marketing decisions

Jev (from TypeSafe AI) is a decision model. It doesn't write text. You give it some text (the *state*) and typed questions, and it returns an answer to each with a probability and a confidence score. That makes it fast and cheap for the yes/no and pick-one calls that fill marketing ops.

This skill helps you:

1. turn a marketing decision into a Jev **recipe** (a JSON file of questions),
2. run that recipe over a CSV with `scripts/jev_batch.py`,
3. sort every row into **auto / review / human** bands by confidence,
4. read the results and tune the thresholds.

## Before you start

- The user needs a TypeSafe API key in the `TYPESAFE_API_KEY` environment variable (get one at https://console.typesafe.ai/keys). Never ask them to paste the key into chat or write it into a file in this skill.
- The script needs network access to `api.typesafe.ai`. That works in Claude Code and on the user's own machine. If your environment can't reach it, prepare everything and give the user the exact command to run themselves.
- Check what data is being sent. Lead and reply data can include personal information. Remind the user to check TypeSafe's [legal page](https://docs.typesafe.ai/legal) (privacy policy and data processing agreement) and their own company's data policy before sending real customer data.

## Step 1: Pick or build a recipe

Starter recipes live in `recipes/`:

| Recipe | Decision | Input columns |
| --- | --- | --- |
| `lead-routing.json` | ICP fit, buyer role, sales intent for inbound form fills | company, job_title, industry, message |
| `reply-triage.json` | What an outbound reply is (interested, not now, referral, unsubscribe, etc.) | reply_text |
| `on-message-check.json` | How on-message a draft is, which pillar it supports, unsourced claims | title, content |
| `asset-tagging.json` | Persona and funnel stage for content assets | title, summary |

If one fits, copy it and edit the criteria to match the user's ICP, personas or messaging. Ask the user for that context. Don't guess their ICP.

If none fits, write a new recipe with the same shape:

```json
{
  "name": "Short name",
  "description": "What decision this makes and why",
  "model": "jev-latest",
  "state_columns": ["only", "the", "columns", "the", "questions", "need"],
  "bands": {"act": 0.85, "review": 0.6},
  "questions": {
    "question_id": {"type": "choice", "instructions": "...", "criteria": {"option_id": "description"}},
    "another_id": {"type": "score", "instructions": "...", "criteria": ["level 0", "level 1", "level 2"]},
    "yes_no_id": {"type": "noul", "instructions": "A plain statement that is true or false."}
  }
}
```

Read `references/question-design.md` before writing or editing questions. The most important rules:

- one specific question per question
- spell out boundaries in the criteria
- keep numbers and dates out (do that math in the CRM or spreadsheet)
- put the safest option first
- send only the columns the decision needs, but don't trim away the evidence

## Step 2: Dry run

Show the user exactly what Jev will see before any call:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/jev_batch.py RECIPE.json INPUT.csv --dry-run
```

In chat, use `scripts/jev_batch.py`. Check that the state reads cleanly and that the column names match.

## Step 3: Small test, then the full run

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/jev_batch.py RECIPE.json INPUT.csv --limit 10
python3 ${CLAUDE_SKILL_DIR}/scripts/jev_batch.py RECIPE.json INPUT.csv -o results.csv
```

The output CSV keeps every original column and adds, for each question, the answer, its confidence and its band. It also adds `row_action` (the lowest band in the row) and `jev_model` (the exact model version that ran). The script prints the band counts and an estimated cost.

## Optional: score against an answer key

If the user has labeled rows (or wants to try the bundled 50-lead test set, `examples/sample-leads-50.csv` with `examples/sample-leads-50-answer-key.csv` in the repo), grade the run:

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/score_results.py results.csv answer-key.csv
```

The answer key needs the same id column as the input plus one column per question. Use `a|b` when either answer is acceptable, and `*` to skip. Lead with accuracy inside the auto band and any wrong answers that slipped through on auto. Those decide whether the thresholds are safe.

## Step 4: Read the results with the user

Summarize:

- how many rows are auto, review and human
- what the auto rows decided (counts per answer)
- a few review and human rows, with why they were unsure

Then suggest next steps:

- **Spot-check the auto band.** If anything there is wrong, raise `act` or tighten the criteria.
- **Lots in human?** The criteria are probably vague. Rewrite them, don't just lower the thresholds.
- **Pin the version.** Once results look right, set `"model"` to the version shown in `jev_model` so updates don't shift results.
- **Act on bands, not decimals.** Re-runs can differ in the second decimal.

## What Jev is not for

It doesn't generate copy, do arithmetic, compare dates, or reason through multi-step logic. Use Claude for writing and analysis, and Jev for the fast, repeatable decision in the middle of a workflow.

## Reference

- TypeSafe docs: https://docs.typesafe.ai
- Quick start: https://docs.typesafe.ai/introduction/quickstart
- API reference: https://docs.typesafe.ai/api/system-one
- Question types: https://docs.typesafe.ai/primitives
- Confidence: https://docs.typesafe.ai/confidence
- Confidence-gated routing: https://docs.typesafe.ai/patterns/confidence-routing
- Known weaknesses: https://docs.typesafe.ai/model-jaggedness/jev-1.13
- Developers can also add TypeSafe's official coding-agent skill: https://github.com/typesafe-ai/skills
