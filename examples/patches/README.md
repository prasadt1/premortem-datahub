# Sample repair patches

Generated from the frozen eval corpus (`order_status` → `order_state` on
`order_history`) via `premortem.rewrite`. Only subject-bound HARD/SOFT refs
are rewritten. CLEARED / UNKNOWN / SELECT * / incomplete-with-star are refused.

Reproduce:

```bash
python eval/run_repair_roundtrip.py   # must report 100% on eligible
premortem --queries-dir eval/corpus --rename order_status:order_state \
  --subject-table order_history --tables-json eval/schema.json \
  --emit-patches /tmp/premortem-patches
```

`write_payload` is unchanged — repairs are a sibling artifact.
