# Media

Diagrams for the README, the Devpost article, and the submission gallery.

**SVG is the source. PNG is generated — never hand-edit a PNG.**

| File | What it shows | Used in |
|---|---|---|
| `customer-journey` | Persona + five-step path from PR to Quality-tab write-back | Devpost inline · gallery · Pages |
| `binding-problem` | Two tables carry `order_status`; name matching flags the wrong one, binding clears it | Devpost inline · gallery · README |
| `verdict-taxonomy` | HARD / SOFT / UNKNOWN / CLEARED, each with a real query | Devpost inline · gallery |
| `dual-mcp-flow` | DataHub's MCP server and Premortem's in one agent session | Devpost inline · gallery |
| `eval-results` | HARD precision and decoy false-alarm rate vs both baselines | Devpost inline · gallery |

## Regenerating

```bash
cd docs/media
for f in customer-journey binding-problem dual-mcp-flow eval-results verdict-taxonomy; do
  rsvg-convert -w 1800 -h 1200 -b '#fcfcfb' "$f.svg" -o "$f.png"
done
```

### Eval explorer data

The Pages [eval explorer](../eval-explorer.html) is driven by generated JSON/JS —
see [EVAL_EXPLORER.md](../EVAL_EXPLORER.md). From the repo root:

```bash
python tools/generate_eval_explorer.py
```

1800×1200 is 3:2 — Devpost's recommended gallery ratio, and large enough to stay
crisp when a judge opens an image full-screen.

## Design constraints

- **Light surface only** (`#fcfcfb`). These render on Devpost's light page and as
  light cards on GitHub in either theme.
- **Status colors never carry meaning alone** — every HARD/SOFT/UNKNOWN/CLEARED
  marker ships with an icon *and* a text label.
- Palette validated for light mode (categorical slots 1–3, all-pairs): worst CVD
  ΔE 9.2, worst normal-vision ΔE 24.0. Aqua sits below 3:1 on this surface, so
  direct value labels are required and present on every bar.
- System sans throughout; monospace only for SQL and identifiers.

## If a number changes

`eval-results.svg` hardcodes 0.40 / 0.44 / 1.00 and 1.00 / 0.83 / 0.00, and
`binding-problem.svg` hardcodes 0.50 → 0.00. Re-run `python eval/run_eval.py`
before submitting and update both if anything moved — the article and the video
quote the same figures.
