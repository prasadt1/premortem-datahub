# Premortem demo — voiceover script (mute visual track)

**Visual:** `docs/video/out/premortem-demo-mute.mp4` (~2:30–2:50)  
**Open:** Premortem title only — **no** DataHub login on camera.  
**Pace:** ~150 wpm. Speak in your own words; timings ±3s are fine. Hard limit **3:00**.

Product coverage in this cut: problem → binding → DataHub → dual MCP / rehearse → HARD/SOFT/UNKNOWN/CLEARED → notify → repair → gate → Quality write-back → eval → architecture.

---

## Beat 1 — Cold open · 0:00–0:12

**On screen:** PREMORTEM title card (orange bar, no logo image)

**Say:**

> Schema changes break things people trust — dashboards, metrics, reports — and the person who renamed the column is rarely the one who finds out first. That Slack thread is the incident. I wanted the blast radius *before* merge, written back so the next engineer inherits it.

---

## Beat 2 — The gap · 0:12–0:35

**On screen:** binding-problem diagram → DataHub ORDER_HISTORY (Lineage if it opens; Columns is fine)

**Say:**

> DataHub Impact Analysis already lists what is connected. What it can't tell you is which consumer queries actually break — or when the same column *name* is a false alarm on another table. Premortem binds each reference to a real table before it scores blast radius.

*(If you see `order_status` on the Columns tab: “Here's the column I'm about to rename on ORDER_HISTORY.”)*

---

## Beat 3 — Rehearse · 0:35–0:55

**On screen:** dual-MCP diagram → CLI `premortem --live`

**Say:**

> One composition path with DataHub: MCP and the Agent Context Kit read schema, lineage, and query history. Premortem rehearses the rename — same core the Premortem MCP tool calls. Ten queries. Three dependents. Everything from the catalog, not a hand-written config.

---

## Beat 4 — Verdicts · 0:55–1:25

**On screen:** forecast overview → UNKNOWN hold → CLEARED hold → Notify section

**Say:**

> Five queries break hard — the column is in a `WHERE`, so a careless fix changes which rows come back. Two are soft: select-list only.
>
> This one needs a human — unqualified column, two tables in scope — so it isn't guessed.
>
> This one is cleared: same name, but it binds to `shipments`, not the table I'm changing. Name matching would have flagged a false alarm.
>
> And Premortem surfaces who to warn — dataset owners from DataHub — before Friday.

---

## Beat 5 — Act · 1:25–2:05

**On screen:** repair patch → gate exit 1 → product-workflow → Quality tab (PREMORTEM SCHEMA REHEARSAL failing)

**Say:**

> Then it acts. Repair patches what it's sure about — subject-bound HARD and SOFT only — and refuses CLEARED, UNKNOWN, and ambiguous binds. Twenty-two of twenty-two eligible patches on the frozen corpus.
>
> `premortem gate` fails the PR when HARD or UNKNOWN would ship — unread SQL cannot silent-pass.
>
> On confirmation the forecast writes back to DataHub: tag and description through DataHub's MCP mutations; the custom assertion through GraphQL. It lands on the Quality tab. The next engineer inherits the rehearsal — they don't learn from a broken dashboard.

---

## Beat 6 — Receipts · 2:05–2:20

**On screen:** eval-results chart

**Say:**

> Why believe it. Forty queries labelled before the classifier that grades against them. HARD precision one point zero. Decoy false alarms zero. One miss left in, unfixed. An adjudicator that measured worse than nothing ships off.

---

## Beat 7 — Close · 2:20–2:35

**On screen:** architecture → title card

**Say:**

> None of this replaces DataHub — it composes with it. Catalog-agnostic binder core, DataHub at the edge. Premortem is the rehearsal before you merge. Apache-2.0 — repo and project page linked on the submission.

---

## Mux after you record VO

```bash
ffmpeg -y -i docs/video/out/premortem-demo-mute.mp4 -i vo.m4a \
  -c:v copy -c:a aac -shortest docs/video/out/premortem-demo-final.mp4
```

## Re-capture

```bash
export DATAHUB_TELEMETRY_ENABLED=false PYTHONWARNINGS=ignore
.venv/bin/premortem --live --rename order_status:order_state \
  --out /tmp/premortem-forecast.md --json-out /tmp/premortem-forecast.json
.venv/bin/python tools/record_demo_visual.py
```
