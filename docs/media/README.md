# Media

Diagrams for the README, the Devpost article, and the submission gallery.

**SVG is the source. PNG is generated — never hand-edit a PNG.**

| File | What it shows | Used in |
|---|---|---|
| `binding-problem` | Two tables carry `order_status`; name matching flags the wrong one, binding clears it | Devpost inline · gallery · README · Pages |
| `customer-journey` | Persona + core path: PR → Impact Analysis → agent → forecast → write-back | Devpost inline · gallery · Pages |
| `product-workflow` | Full verbs after forecast: **repair → gate → notify → write-back** (+ refuse ethic) | Devpost gallery |
| `verdict-taxonomy` | HARD / SOFT / UNKNOWN / CLEARED, each with a real query | Devpost gallery |
| `eval-results` | HARD precision and decoy false-alarm rate vs both baselines | Devpost gallery · Pages |
| `architecture` | Layered: pure classifier core, one binder shared by classify+repair, CatalogClient ×3, DataHub edge | Devpost inline · gallery · Pages · README |
| `dual-mcp-flow` | DataHub's MCP server and Premortem's in one agent session | Devpost gallery · Pages |
| `gallery/*.png` | **Framed canvases** for Devpost upload (brand + caption panel) | Devpost gallery only — regenerate with `python tools/frame_gallery_images.py` |

## Regenerating

```bash
cd docs/media
for f in binding-problem customer-journey product-workflow verdict-taxonomy eval-results architecture dual-mcp-flow; do
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
