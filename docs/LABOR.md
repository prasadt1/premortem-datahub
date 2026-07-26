# Labor split (Privilege pattern)

| Role | Owner |
|------|--------|
| Verification gates (DataHub write-back, queries, CRDB vector/GC, Bedrock) | **You** |
| Specs, plans, scaffold, implementation, iteration | **Cursor** |
| Seam reviews: patched specs vs ground truth, frozen eval design, demo/positioning, pre-submit judge pass | **Claude** |
| Decisions, own-voice README lines, video | **You** |

Cursor drives. Claude gates at seams. No exhaustive Claude-only specs ahead of live platform truth.
