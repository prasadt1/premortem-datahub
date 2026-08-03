# Demo video (mute visual + VO script)

| File | What |
|---|---|
| [`out/premortem-demo-mute.mp4`](out/premortem-demo-mute.mp4) | Mute visual (~2:38) — opens on Premortem title (login is off-camera) |
| [`vo-script.md`](vo-script.md) | Beat-by-beat voiceover lines + timestamps |
| [`../video-guide.md`](../video-guide.md) | Full shot guide / preflight (local draft; may be gitignored) |

## How to finish

1. Open `out/premortem-demo-mute.mp4` and play while recording VO (or import into CapCut / Descript).
2. Read `vo-script.md` beat by beat — rewrite in your own words.
3. Mux:

```bash
ffmpeg -y -i docs/video/out/premortem-demo-mute.mp4 -i vo.m4a \
  -c:v copy -c:a aac -shortest docs/video/out/premortem-demo-final.mp4
```

4. Upload to YouTube (public), set thumbnail `docs/media/thumbnail-youtube-1080.png`, paste URL into Devpost + draft.

## Re-capture visuals

Needs DataHub UI `:9002` + GMS `:8080` (Quickstart login `datahub` / `datahub`).

```bash
export DATAHUB_TELEMETRY_ENABLED=false PYTHONWARNINGS=ignore
.venv/bin/premortem --live --rename order_status:order_state \
  --out /tmp/premortem-forecast.md --json-out /tmp/premortem-forecast.json
.venv/bin/python tools/record_demo_visual.py
```

**Not automated:** live Claude Code keystrokes. The mute track uses dual-MCP diagram + CLI that calls the same core — VO script has the honest wording. Optionally splice your own Claude Code clip over Beat 3.
