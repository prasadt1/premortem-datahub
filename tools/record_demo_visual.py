#!/usr/bin/env python3
"""Record a mute Premortem demo visual for voiceover later.

Auth happens in a *non-recording* context first (so login is never on camera).
Opens on the Premortem title card — never the DataHub login wall.

Requires: DataHub UI :9002, GMS :8080, playwright + chromium.
Produces: docs/video/out/premortem-demo-mute.{webm,mp4}
"""
from __future__ import annotations

import html as html_mod
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "video" / "out"
CLIPS = OUT / "clips"
STATE = OUT / "datahub-state.json"
FORECAST = Path("/tmp/premortem-forecast.md")
URN = (
    "urn:li:dataset:(urn:li:dataPlatform:snowflake,"
    "b2fd91.order_entry_db.analytics.order_history,PROD)"
)
DATASET_URL = (
    "http://localhost:9002/dataset/"
    + URN.replace("(", "%28").replace(")", "%29").replace(":", "%3A").replace(",", "%2C")
    + "/"
)
DATASET_URL_RAW = f"http://localhost:9002/dataset/{URN}/"
ARCH = ROOT / "docs" / "media" / "architecture.png"
DUAL = ROOT / "docs" / "media" / "dual-mcp-flow.png"
BINDING = ROOT / "docs" / "media" / "binding-problem.png"
WORKFLOW = ROOT / "docs" / "media" / "product-workflow.png"
EVAL_PNG = ROOT / "docs" / "media" / "eval-results.png"
PATCH = ROOT / "examples" / "patches" / "q01.patch"
VW, VH = 1920, 1080


def wait(page, seconds: float) -> None:
    page.wait_for_timeout(int(seconds * 1000))


def hold_image(page, path: Path, seconds: float, caption: str = "") -> None:
    if not path.exists():
        page.set_content(
            f"<html><body style='background:#0b0b0b;color:#fcfcfb;font:24px system-ui;padding:48px'>{caption or path.name}</body></html>"
        )
        wait(page, seconds)
        return
    # Serve via data URL so file:// never breaks in Chromium
    import base64

    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    src = f"data:{mime};base64,{b64}"
    page.set_content(
        f"""<!doctype html><html><body style="margin:0;background:#0b0b0b;display:flex;flex-direction:column;align-items:center;justify-content:center;height:100vh;font-family:system-ui,sans-serif;color:#fcfcfb">
        <p style="margin:0 0 16px;font-size:20px;color:#eb6834;letter-spacing:.08em;text-transform:uppercase">{html_mod.escape(caption)}</p>
        <img src="{src}" alt="" style="max-width:92vw;max-height:82vh;object-fit:contain"/>
        </body></html>"""
    )
    wait(page, seconds)


def hold_title(page, seconds: float, subtitle: str = "") -> None:
    """Clean title card — CSS only, no image embeds."""
    sub = html_mod.escape(subtitle) if subtitle else "how it breaks, before you merge"
    page.set_content(
        f"""<!doctype html><html><head><meta charset="utf-8"/></head>
        <body style="margin:0;background:#0b0b0b;height:100vh;font-family:system-ui,-apple-system,sans-serif;color:#fcfcfb">
        <div style="position:absolute;left:0;top:0;bottom:0;width:12px;background:#eb6834"></div>
        <div style="display:flex;flex-direction:column;justify-content:center;height:100vh;padding:0 80px;max-width:1200px;box-sizing:border-box">
          <p style="margin:0 0 20px;font-size:18px;font-weight:700;color:#eb6834;letter-spacing:0.14em">DATAHUB x PREMORTEM</p>
          <h1 style="margin:0;padding:0;font-size:72px;font-weight:700;letter-spacing:-0.02em;line-height:1">PREMORTEM</h1>
          <p style="margin:18px 0 0;padding:0;font-size:28px;color:#b0aea6;line-height:1.3">{sub}</p>
          <div style="margin-top:48px;display:flex;gap:14px;align-items:stretch">
            <div style="flex:1;border:2px solid #2a78d6;border-radius:12px;padding:18px 20px;background:#161614">
              <div style="font-size:13px;font-weight:700;color:#2a78d6;letter-spacing:0.08em">DATAHUB</div>
              <div style="margin-top:8px;font-size:20px;font-weight:600">Impact Analysis</div>
              <div style="margin-top:6px;font-size:15px;color:#898781">what is connected</div>
            </div>
            <div style="display:flex;align-items:center;color:#eb6834;font-size:28px;font-weight:700">&#8594;</div>
            <div style="flex:1;border:2px solid #eb6834;border-radius:12px;padding:18px 20px;background:#161614">
              <div style="font-size:13px;font-weight:700;color:#eb6834;letter-spacing:0.08em">PREMORTEM</div>
              <div style="margin-top:8px;font-size:20px;font-weight:600">Per-query forecast</div>
              <div style="margin-top:6px;font-size:15px;color:#898781">HARD · SOFT · UNKNOWN · CLEARED</div>
            </div>
          </div>
        </div>
        </body></html>"""
    )
    wait(page, seconds)


def show_forecast(page, seconds: float, highlight: str | None = None) -> None:
    text = FORECAST.read_text(encoding="utf-8") if FORECAST.exists() else "Forecast missing"
    safe = html_mod.escape(text)
    if highlight == "unknown":
        safe = safe.replace(
            "UNKNOWN / needs human (1)",
            '<mark style="background:#efe6d4;color:#6a5220">UNKNOWN / needs human (1)</mark>',
        )
    elif highlight == "cleared":
        safe = safe.replace(
            "CLEARED (references a same-named column that binds elsewhere) (1)",
            '<mark style="background:#dde7ef;color:#243f55">CLEARED … (1)</mark>',
        ).replace(
            "decoy_shipments_order_status",
            '<mark style="background:#dde7ef;color:#243f55">decoy_shipments_order_status</mark>',
        )
    elif highlight == "notify":
        safe = safe.replace(
            "Notify (who to warn before Friday)",
            '<mark style="background:#e4ebe3;color:#2f4f38">Notify (who to warn before Friday)</mark>',
        )
    scroll = {"cleared": 220, "notify": 420, "unknown": 120}.get(highlight or "", 0)
    page.set_content(
        f"""<!doctype html><html><body style="margin:0;background:#141311;color:#f2efe7;font-family:ui-monospace,Menlo,monospace">
        <div style="padding:28px 40px 40px">
          <p style="margin:0 0 12px;font-family:system-ui;font-size:14px;color:#eb6834;letter-spacing:.08em">LIVE FORECAST · premortem --live</p>
          <pre style="margin:0;font-size:19px;line-height:1.45;white-space:pre-wrap">{safe}</pre>
        </div>
        <script>window.scrollTo(0, {scroll});</script>
        </body></html>"""
    )
    wait(page, seconds)


def show_cli(page, seconds: float) -> None:
    page.set_content(
        """<!doctype html><html><body style="margin:0;background:#0b0b0b;color:#d7d5ce;font-family:ui-monospace,Menlo,monospace;padding:40px">
        <p style="color:#eb6834;font-family:system-ui;letter-spacing:.08em;font-size:14px">REHEARSE · same core the Premortem MCP server calls</p>
        <pre style="font-size:22px;line-height:1.5;margin-top:24px">$ premortem --live --rename order_status:order_state

# queries=10  downstream=3
HARD (5) · SOFT (2) · UNKNOWN (1) · CLEARED (1)
wrote forecast.md</pre>
        </body></html>"""
    )
    wait(page, seconds)


def show_repair(page, seconds: float) -> None:
    patch = PATCH.read_text(encoding="utf-8") if PATCH.exists() else "- order_status\n+ order_state"
    page.set_content(
        f"""<!doctype html><html><body style="margin:0;background:#0b0b0b;color:#d7d5ce;font-family:ui-monospace,Menlo,monospace;padding:40px">
        <p style="color:#eb6834;font-family:system-ui;letter-spacing:.08em;font-size:14px">REPAIR · subject-bound HARD/SOFT only · 22/22 eligible</p>
        <pre style="font-size:22px;line-height:1.5;margin-top:20px;color:#fab219">{html_mod.escape(patch)}</pre>
        <p style="margin-top:28px;font-family:system-ui;font-size:20px;color:#b0aea6">CLEARED · UNKNOWN · SELECT * · ambiguous binds → <span style="color:#898781">refused</span> (no invented patch)</p>
        </body></html>"""
    )
    wait(page, seconds)


def show_gate(page, seconds: float) -> None:
    page.set_content(
        """<!doctype html><html><body style="margin:0;background:#0b0b0b;color:#d7d5ce;font-family:ui-monospace,Menlo,monospace;padding:48px">
        <p style="color:#eb6834;font-family:system-ui;letter-spacing:.08em;font-size:14px">GATE · fail the PR before merge</p>
        <pre style="font-size:24px;line-height:1.55;margin-top:20px">$ premortem gate --fail-on hard,unknown

HARD findings present — failing the PR.
UNKNOWN findings present — unread SQL cannot silent-pass.

<span style="color:#d03b3b">exit code 1</span></pre>
        </body></html>"""
    )
    wait(page, seconds)


def datahub_login(page) -> bool:
    try:
        page.goto("http://localhost:9002/", wait_until="domcontentloaded", timeout=20000)
        wait(page, 1.5)
        body = page.inner_text("body")[:1500]
        if "Welcome to DataHub" not in body and "Username" not in body:
            return True
        page.locator('input[type="text"], input[name="username"]').first.fill("datahub")
        page.locator('input[type="password"]').first.fill("datahub")
        wait(page, 0.2)
        btn = page.get_by_role("button", name="Login")
        if btn.count() == 0:
            btn = page.locator("button:has-text('Login')")
        btn.first.click(timeout=5000)
        wait(page, 3.0)
        return "Username" not in page.inner_text("body")[:600]
    except Exception as e:
        print(f"login failed: {e}", file=sys.stderr)
        return False


def open_order_history(page) -> bool:
    for url in (DATASET_URL_RAW, DATASET_URL):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            wait(page, 2.5)
            body = page.inner_text("body")[:2500]
            if "Welcome to DataHub" in body or "Username" in body[:400]:
                return False
            if "order_history" in body.lower() or "ORDER_HISTORY" in body:
                return True
        except Exception as e:
            print(f"open dataset failed: {e}", file=sys.stderr)
    try:
        page.goto("http://localhost:9002/search?query=ORDER_HISTORY%20snowflake", wait_until="domcontentloaded", timeout=20000)
        wait(page, 2.5)
        page.get_by_text("ORDER_HISTORY", exact=False).first.click(timeout=5000)
        wait(page, 2.5)
        return "order_history" in page.inner_text("body")[:2500].lower()
    except Exception as e:
        print(f"search fallback failed: {e}", file=sys.stderr)
        return False


def click_tab(page, tab: str) -> None:
    for sel in (
        lambda: page.get_by_role("tab", name=tab).first,
        lambda: page.locator(f"[role='tab']:has-text('{tab}')").first,
        lambda: page.locator(f"text='{tab}'").first,
    ):
        try:
            loc = sel()
            loc.click(timeout=4000)
            wait(page, 1.5)
            return
        except Exception:
            continue
    print(f"tab click '{tab}' failed", file=sys.stderr)


def try_datahub(page, tab: str, seconds: float) -> bool:
    if not open_order_history(page):
        return False
    click_tab(page, tab)
    wait(page, max(seconds - 3.0, 5.0))
    body = page.inner_text("body")[:3500]
    return any(
        s.lower() in body.lower()
        for s in ("ORDER", "Quality", "Lineage", "Assertion", "premortem", "Downstream", "Impact", "order_status")
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if CLIPS.exists():
        shutil.rmtree(CLIPS)
    CLIPS.mkdir(parents=True, exist_ok=True)
    if not FORECAST.exists():
        print("Missing /tmp/premortem-forecast.md — run premortem --live first", file=sys.stderr)
        return 1

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        # ── Auth OFF camera ──────────────────────────────────────────
        boot = browser.new_context(viewport={"width": VW, "height": VH})
        boot_page = boot.new_page()
        if not datahub_login(boot_page):
            print("DataHub login failed — Quality/Lineage shots will use diagram fallbacks", file=sys.stderr)
        boot.storage_state(path=str(STATE))
        boot.close()

        # ── Recording context (starts AFTER login) ───────────────────
        context = browser.new_context(
            viewport={"width": VW, "height": VH},
            storage_state=str(STATE) if STATE.exists() else None,
            record_video_dir=str(CLIPS),
            record_video_size={"width": VW, "height": VH},
        )
        page = context.new_page()

        # 1. Cold open — Premortem only
        hold_title(page, 12, "how it breaks, before you merge")

        # 2. Problem / differentiator
        if BINDING.exists():
            hold_image(page, BINDING, 10, "The gap: name match vs binding")
        ok = try_datahub(page, "Lineage", 12)
        if not ok:
            # Still show the dataset (Columns is fine) then fall back diagram
            if not try_datahub(page, "Columns", 8):
                hold_image(page, WORKFLOW, 10, "Impact Analysis lists connections — not how they break")

        # 3. Rehearse via composition path
        if DUAL.exists():
            hold_image(page, DUAL, 7, "Compose with DataHub · dual MCP")
        show_cli(page, 10)

        # 4. Forecast: overview → UNKNOWN → CLEARED → notify
        show_forecast(page, 7, highlight=None)
        show_forecast(page, 8, highlight="unknown")
        show_forecast(page, 8, highlight="cleared")
        show_forecast(page, 6, highlight="notify")

        # 5. Act: repair → gate → write-back
        show_repair(page, 9)
        show_gate(page, 7)
        if WORKFLOW.exists():
            hold_image(page, WORKFLOW, 7, "repair · gate · notify · write-back")
        ok_q = try_datahub(page, "Quality", 14)
        if not ok_q and WORKFLOW.exists():
            hold_image(page, WORKFLOW, 10, "Write-back lands on DataHub Quality")

        # 6. Receipts
        if EVAL_PNG.exists():
            hold_image(page, EVAL_PNG, 12, "Frozen eval · HARD prec 1.00 · decoy FP 0.00")

        # 7. Close
        if ARCH.exists():
            hold_image(page, ARCH, 8, "Catalog-agnostic core · composes with DataHub")
        hold_title(page, 8, "Apache-2.0 · before a dashboard finds the break")

        context.close()
        browser.close()

    videos = sorted(CLIPS.glob("*.webm"), key=lambda p: p.stat().st_mtime)
    if not videos:
        print("No video recorded", file=sys.stderr)
        return 1
    dest_webm = OUT / "premortem-demo-mute.webm"
    shutil.copy(videos[-1], dest_webm)
    print(f"Wrote {dest_webm} ({dest_webm.stat().st_size // 1024} KB)")

    dest_mp4 = OUT / "premortem-demo-mute.mp4"
    if shutil.which("ffmpeg"):
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(dest_webm),
                "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(dest_mp4),
            ],
            check=False,
        )
        if dest_mp4.exists():
            print(f"Wrote {dest_mp4} ({dest_mp4.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
