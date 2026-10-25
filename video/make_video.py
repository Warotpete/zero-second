"""Record the Zero Second demo video, scene by scene, against a running local app.

    python video/tts.py          # narration clips (Azure AI Speech)
    python video/make_video.py   # records scenes with Playwright, muxes voice, stitches the MP4

Needs the API on http://127.0.0.1:8000 (with Foundry configured) and the web app built.
"""

from __future__ import annotations

import json
import shutil
import sys
import subprocess
import time
import urllib.request
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
CARDS = (HERE / "cards").as_uri()
APP = "http://127.0.0.1:8000"
W, H = 1600, 900
PAD = 1.1  # seconds of breathing room after each narration line
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

CURSOR_JS = """
(() => {
  const add = () => {
    if (document.getElementById('zs-cursor')) return;
    const c = document.createElement('div');
    c.id = 'zs-cursor';
    Object.assign(c.style, {position:'fixed', width:'22px', height:'22px', borderRadius:'50%', border:'3px solid #00ff85',
      background:'rgba(0,255,133,.25)', zIndex:2147483647, pointerEvents:'none', transform:'translate(-50%,-50%)',
      transition:'left .35s ease, top .35s ease', left:'-50px', top:'-50px'});
    document.body.appendChild(c);
    addEventListener('mousemove', e => { c.style.left = e.clientX + 'px'; c.style.top = e.clientY + 'px'; }, true);
    addEventListener('mousedown', () => { c.style.background = 'rgba(0,255,133,.8)'; setTimeout(() => c.style.background = 'rgba(0,255,133,.25)', 250); }, true);
  };
  if (document.body) add(); else addEventListener('DOMContentLoaded', add);
})();
"""


# ------------------------------------------------------------------ API helpers
def api(path: str, body: dict | None = None):
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(APP + path, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())


def state(room: str) -> dict:
    return api(f"/api/rooms/{room}/state")


def wait_for(cond, timeout=240, what="condition"):
    t = time.time()
    while time.time() - t < timeout:
        try:
            if cond():
                return
        except Exception:
            pass
        time.sleep(2)
    raise TimeoutError(f"timed out waiting for {what}")


def content_ready(room: str, sid: str) -> bool:
    c = state(room)["content"].get(sid)
    return bool(c and c["state"] in ("ready", "pre_approved", "published"))


def prepare() -> None:
    print("preparing rooms ...")
    api("/api/rooms/video/new", {})
    api("/api/rooms/video/control", {"action": "autopilot", "value": 0})
    api("/api/rooms/video/jump", {"minute": 60})
    wait_for(lambda: content_ready("video", "HFC-09-ms50"), what="Mendes content")
    api("/api/rooms/videofault/new", {})
    api("/api/rooms/videofault/control", {"action": "fault", "value": 1})
    api("/api/rooms/videofault/jump", {"minute": 30})

    def fault_done():
        for tr in state("videofault")["traces"].values():
            kinds = [t["kind"] for t in tr]
            if "reject" in kinds and any(t["lane"] == "Verifier agent" and t["kind"] == "ok" for t in tr[kinds.index("reject"):]):
                return True
        return False

    wait_for(fault_done, what="fault-injection trace")
    api("/api/rooms/seedshow/new", {"seed": 4821})
    api("/api/rooms/seedshow/jump", {"minute": 70})
    print("rooms ready")


# ------------------------------------------------------------------ recording
def captions_js(text: str, seconds: float) -> str:
    sentences = [s.strip() for s in text.replace("?", "?|").replace(". ", ".|").replace(": ", ":|").split("|") if s.strip()]
    words = [max(1, len(s.split())) for s in sentences]
    total = sum(words)
    timeline, acc = [], 0.4
    for s, w in zip(sentences, words):
        timeline.append([round(acc * 1000), s])
        acc += (seconds - PAD) * w / total
    return """
(() => {
  const old = document.getElementById('zs-cap'); if (old) old.remove();
  const box = document.createElement('div'); box.id = 'zs-cap';
  Object.assign(box.style, {position:'fixed', left:'50%', bottom:'26px', transform:'translateX(-50%)', maxWidth:'1240px',
    background:'rgba(18,0,22,.86)', color:'#fff', font:'600 26px/1.3 Outfit, system-ui, sans-serif', padding:'10px 22px',
    borderRadius:'12px', zIndex:2147483646, textAlign:'center', pointerEvents:'none', borderBottom:'3px solid #00ff85'});
  document.body.appendChild(box);
  for (const [ms, s] of __TIMELINE__) setTimeout(() => { box.textContent = s; }, ms);
})();
""".replace("__TIMELINE__", json.dumps(timeline))


def record(browser, scene: dict, seconds: float, url: str, actions=None, frame_url: str | None = None) -> Path:
    tmp = BUILD / "raw" / scene["id"]
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    ctx = browser.new_context(viewport={"width": W, "height": H}, record_video_dir=str(tmp),
                              record_video_size={"width": W, "height": H}, device_scale_factor=1)
    ctx.add_init_script(CURSOR_JS)
    page = ctx.new_page()
    t0 = time.monotonic()
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(1500)
    page.evaluate(captions_js(scene["text"], seconds))
    page.mouse.move(W / 2, H / 2)
    start = time.monotonic()
    if actions:
        actions(page)
    left = seconds - (time.monotonic() - start)
    if left > 0:
        page.wait_for_timeout(left * 1000)
    end = time.monotonic()
    video = page.video
    ctx.close()
    src = Path(video.path())
    out = BUILD / f"{scene['id']}.mp4"
    offset = start - t0
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-ss", f"{offset:.2f}", "-i", str(src),
                    "-i", str(BUILD / f"{scene['id']}.mp3"),
                    "-filter_complex", f"[1:a]adelay=400|400,apad[a];[0:v]scale=1920:1080:flags=lanczos,fps=30,format=yuv420p[v]",
                    "-map", "[v]", "-map", "[a]", "-t", f"{end - start:.2f}",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k", "-ar", "48000", str(out)],
                   check=True)
    print(f"recorded {scene['id']:14s} {end - start:5.1f}s")
    return out


def slow_click(page: Page, locator, pause=900):
    box = locator.bounding_box()
    if box:
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=12)
        page.wait_for_timeout(350)
    locator.click()
    page.wait_for_timeout(pause)


def hover(page: Page, locator, pause=900):
    box = locator.bounding_box()
    if box:
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=12)
    page.wait_for_timeout(pause)


def row(page: Page, title: str):
    return page.locator("tr", has_text=title).first


# ------------------------------------------------------------------ scenes
def main() -> None:
    cfg = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    timing = json.loads((BUILD / "timing.json").read_text(encoding="utf-8"))
    scenes = {s["id"]: s for s in cfg["scenes"]}
    dur = {k: v + 0.4 + PAD for k, v in timing.items()}
    if "--no-prepare" not in sys.argv:
        prepare()
    clips: list[Path] = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        clips.append(record(browser, scenes["s01_title"], dur["s01_title"], f"{CARDS}/title.html"))

        def s02(page: Page):
            for t in ("Northvale revenge", "Okafor – 10th", "Mendes – 50th club goal"):
                hover(page, row(page, t), 2600)

        clips.append(record(browser, scenes["s02_desk"], dur["s02_desk"], f"{APP}/desk?room=video", s02))

        def s03(page: Page):
            slow_click(page, page.locator(".seg button", has_text="66'"), 2500)
            slow_click(page, row(page, "Mendes – 50th club goal"), 3000)
            for tab in ("Casual", "Overlay", "Analyst"):
                slow_click(page, page.locator(".tabs button", has_text=tab), 2600)

        clips.append(record(browser, scenes["s03_prepared"], dur["s03_prepared"], f"{APP}/desk?room=video", s03))

        def s04(page: Page):
            hover(page, row(page, "Mendes – 50th club goal"), 600)
            page.locator("tr", has_text="Mendes – 50th club goal").first.click()
            page.wait_for_timeout(500)
            page.keyboard.press("a")
            page.wait_for_timeout(800)

        clips.append(record(browser, scenes["s04_approve"], dur["s04_approve"], f"{APP}/desk?room=video", s04))

        def s05(page: Page):
            page.locator("tr", has_text="Mendes – 50th club goal").first.click()
            slow_click(page, page.locator(".seg button", has_text="78'"), 1500)
            hover(page, row(page, "Mendes – 50th club goal"), 1200)
            hover(page, page.locator(".copybox").first, 1500)

        clips.append(record(browser, scenes["s05_goal"], dur["s05_goal"], f"{APP}/desk?room=video", s05))

        fan = f"{APP}/fan?room=video"

        def s06(page: Page):
            fr = page.frame_locator("#fan")
            page.wait_for_timeout(1200)
            slow_click(page, fr.locator(".seg button", has_text="Analyst"), 2200)
            fr.locator("body").evaluate("() => document.scrollingElement.scrollBy({top: 260, behavior: 'smooth'})")

        clips.append(record(browser, scenes["s06_fan"], dur["s06_fan"], f"{CARDS}/phone.html?src={fan}", s06))

        def s07(page: Page):
            fr = page.frame_locator("#fan")
            slow_click(page, fr.locator(".tabs button", has_text="Watch for"), 3500)
            fr.locator("body").evaluate("() => document.scrollingElement.scrollBy({top: 520, behavior: 'smooth'})")
            page.wait_for_timeout(2500)

        clips.append(record(browser, scenes["s07_watch"], dur["s07_watch"], f"{CARDS}/phone.html?src={fan}", s07))

        def s08(page: Page):
            page.wait_for_timeout(1500)
            rej = page.locator(".step.reject").first
            hover(page, rej, 2500)
            hover(page, page.locator(".step.verified").first, 2000)
            page.mouse.wheel(0, 500)

        clips.append(record(browser, scenes["s08_fault"], dur["s08_fault"], f"{APP}/desk/trace?room=videofault", s08))

        api("/api/rooms/video/jump", {"minute": 91})
        wait_for(lambda: state("video")["recap"] is not None, what="recap")

        def s09(page: Page):
            page.wait_for_timeout(3500)
            page.mouse.move(W * 0.3, H * 0.6)
            page.mouse.wheel(0, 600)
            page.wait_for_timeout(2500)

        clips.append(record(browser, scenes["s09_recap"], dur["s09_recap"], f"{APP}/desk/recap?room=video", s09))
        clips.append(record(browser, scenes["s10_seed"], dur["s10_seed"], f"{APP}/desk?room=seedshow"))
        clips.append(record(browser, scenes["s11_arch"], dur["s11_arch"], f"{CARDS}/arch.html"))
        clips.append(record(browser, scenes["s12_end"], dur["s12_end"], f"{CARDS}/end.html"))
        browser.close()

    listing = BUILD / "concat.txt"
    listing.write_text("".join(f"file '{c.as_posix()}'\n" for c in clips), encoding="utf-8")
    final = HERE / "zero-second-demo.mp4"
    subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
                    "-movflags", "+faststart", str(final)], check=True)
    print("wrote", final)


if __name__ == "__main__":
    main()
