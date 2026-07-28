# S2 assertion (camera)

Exactly **one** custom assertion on the demo ORDER_HISTORY dataset.

- **URN (stable):** `urn:li:assertion:premortem-order-status-rehearsal`
- **Platform category:** Premortem schema rehearsal
- **Result:** FAILURE (with Last Run)
- **externalUrl:** forecast markdown on GitHub
- **fieldPath:** omitted — see [OSS_ISSUES.md](OSS_ISSUES.md) #4

Re-seed idempotently:

```bash
python tools/seed_demo_environment.py
```

Prunes probe duplicates, upserts the stable URN, reports FAILURE, asserts count == 1.
