# Eval explorer

Static page that lists all 40 frozen-eval queries with gold labels vs the
binder-only Premortem verdict (`classify_query` with `subject_table` + schema
tables).

- Page: [eval-explorer.html](./eval-explorer.html)
- Data: `eval-explorer-data.js` (embedded) and `eval-explorer-data.json`
  (same payload) — **generated only**, never hand-edited.

## Regenerating

From the repo root (requires the same deps as `eval/run_eval.py`):

```bash
python tools/generate_eval_explorer.py
```

That rewrites `docs/eval-explorer-data.json` and `docs/eval-explorer-data.js`.
Do not edit those files by hand.
