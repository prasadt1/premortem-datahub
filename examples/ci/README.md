# CI packaging for the Premortem merge gate

Worked example: [`premortem-gate.yml`](premortem-gate.yml).

```bash
premortem gate \
  --queries-dir eval/corpus \
  --rename order_status:order_state \
  --subject-table order_history \
  --tables-json eval/schema.json \
  --fail-on hard
# exit 0 = clean; exit 1 = findings at threshold; JSON summary on stdout
```

Live catalog variant: replace `--queries-dir` / schema flags with `--live` and set
`DATAHUB_GMS_URL` (+ token). No GitHub App — just an exit code and this YAML.
