"""Upscale a finished reel on higgsfield.ai/upscale with Ali's exact settings, invisibly.

    python tools/higgs_upscale.py prepare "<video.mp4>"   # upload + settings + price check, NEVER fires
    python tools/higgs_upscale.py fire    "<video.mp4>"   # only after Ali said yes to the price
    python tools/higgs_upscale.py close                   # shut the hidden Chrome

Settings (Ali, 2026-10-09): Topaz Video, Scale factor 2k, Enhancement ON + preset Proteus
(default Starlight Precise 2.5 is expensive), Parameters Auto, Frame Interpolation ON 60 fps,
Slow motion 1x. Normal price 8-10 credits per reel. NEVER fire above 15 credits: a big number is a
page bug -> click "Original", wait 3 s, click "2k" (82 -> 8 on 2026-10-09).

Runs a dedicated Chrome profile (.browser/higgsfield, Ali logged in once) on the hidden desktop
(tools/_hiddendesk.py) and drives it with Playwright over CDP. Ali's screen, cursor and keyboard
are never touched.
"""
import json
import os
import re
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hiddendesk as hd  # noqa: E402

ECOM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PROFILE = os.path.join(ECOM, ".browser", "higgsfield")
PORT = 9333
URL = "https://higgsfield.ai/upscale"
MAX_CREDITS = 15
STATE = os.path.join(PROFILE, "upscale_state.json")
SHOTS = os.path.join(ECOM, "exports", "_incoming")


def cdp_up():
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=2)
        return True
    except Exception:
        return False


def ensure_chrome():
    if cdp_up():
        return
    if not os.path.exists(os.path.join(PROFILE, "Default")):
        raise SystemExit("Higgsfield profile missing: Ali must log in once (see the upscaling skill, 'first-time login').")
    hd.launch(CHROME, f'--user-data-dir="{PROFILE}" --remote-debugging-port={PORT} --no-first-run '
                      f'--no-default-browser-check --window-size=1600,1000 {URL}')
    for _ in range(40):
        if cdp_up():
            return
        time.sleep(0.5)
    raise SystemExit("hidden Chrome did not start")


def tab_key(video):
    import hashlib
    return "upscale-" + hashlib.sha1(os.path.abspath(video).lower().encode()).hexdigest()[:12]


def page(p, key=None, new=False):
    """One tab per video (2026-10-09, so several upscales can run at once). The tab is tagged with
    window.name = key; `new` opens a fresh tab for a new upload."""
    b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
    ctx = b.contexts[0]
    if key:
        for pg in ctx.pages:
            try:
                if pg.evaluate("() => window.name") == key:
                    return b, pg
            except Exception:
                pass
        if not new:
            raise SystemExit("this file's upscale tab is gone: run 'prepare' again (and re-confirm the price)")
        pg = ctx.new_page()
        return b, pg
    pg = ctx.pages[0] if ctx.pages else ctx.new_page()
    return b, pg


def load_state():
    try:
        st = json.load(open(STATE))
    except Exception:
        return {}
    return st if "video" not in st else {tab_key(st["video"]): st}  # old single-file format


def save_state(key, entry):
    st = load_state()
    st[key] = entry
    json.dump(st, open(STATE, "w"), indent=1)


def cost(pg):
    t = pg.locator("button:has-text('Upscale')").last.inner_text()
    nums = re.findall(r"\d+(?:\.\d+)?", t)
    return float(nums[-1]) if nums else None


def click_text(pg, text, exact=True, wait=1.0):
    pg.get_by_text(text, exact=exact).first.click()
    time.sleep(wait)


def settings_ok(pg):
    body = pg.locator("body").inner_text()
    need = ["Topaz Video", "Proteus"]
    return all(n in body for n in need)


def apply_settings(pg):
    if "Topaz Video" not in pg.locator("body").inner_text():
        click_text(pg, "Select model", wait=1.2)
        click_text(pg, "Topaz Video", wait=1.5)
    click_text(pg, "2k", wait=0.8)
    if not pg.get_by_text("Enhancement", exact=True).count():
        click_text(pg, "Advanced settings", wait=1.2)
    if not pg.get_by_text("Proteus", exact=True).count():
        pg.locator("text=/Starlight|Artemis|Iris|Rhea|Gaia|Theia/").first.click()
        time.sleep(1)
        click_text(pg, "Proteus", wait=1)
    click_text(pg, "Auto", wait=0.6)
    if not pg.get_by_text("60 fps", exact=True).count():  # interpolation switch still off
        pg.get_by_text("Frame Interpolation", exact=True).locator("xpath=..").locator(
            "button, [role=switch], input[type=checkbox]").first.click()
        time.sleep(1.2)
    click_text(pg, "60 fps", wait=1.5)


def fix_price(pg):
    """Ali's fix for an inflated price: Original, wait 3 s, 2k. Returns the final price."""
    c = cost(pg)
    for _ in range(3):
        if c is not None and c <= MAX_CREDITS:
            return c
        click_text(pg, "Original", wait=3)
        click_text(pg, "2k", wait=2)
        c = cost(pg)
    return c


def prepare(video):
    from playwright.sync_api import sync_playwright
    video = os.path.abspath(video)
    if not os.path.exists(video):
        raise SystemExit(f"no such file: {video}")
    ensure_chrome()
    with sync_playwright() as p:
        key = tab_key(video)
        b, pg = page(p, key, new=True)
        pg.goto(URL)
        pg.evaluate(f"() => window.name = '{key}'")
        pg.wait_for_selector("input[type=file]", state="attached", timeout=60000)  # page never goes network-idle
        time.sleep(3)
        for label in ("Opt Out of Targeted Advertising",):
            if pg.get_by_text(label, exact=True).count():
                click_text(pg, label)
        pg.locator("input[type=file]").first.set_input_files(video)
        dur = None
        for _ in range(60):  # wait for the uploaded clip to load in the page
            time.sleep(1)
            v = pg.locator("video")
            if v.count():
                dur = v.first.evaluate("e => e.duration")
                if dur and dur == dur:
                    break
        apply_settings(pg)
        price = fix_price(pg)
        os.makedirs(SHOTS, exist_ok=True)
        shot = os.path.join(SHOTS, f"upscale-settings {os.path.splitext(os.path.basename(video))[0][:60]}.png")
        pg.screenshot(path=shot, clip={"x": 1230, "y": 90, "width": 345, "height": 810})
        save_state(key, {"video": video, "price": price, "duration": dur, "page": pg.url, "at": time.time()})
        ok = settings_ok(pg)
        print(f"READY  {os.path.basename(video)}  ({dur:.2f}s on the page)" if dur else f"READY  {os.path.basename(video)}")
        print(f"settings: Topaz Video, 2k, Proteus, Auto, 60 fps, 1x  ({'verified' if ok else 'CHECK SCREENSHOT'})")
        print(f"PRICE  {price} credits" + ("" if price is not None and price <= MAX_CREDITS else
                                           f"  -> ABOVE {MAX_CREDITS}: do NOT fire, tell Ali"))
        print(f"screenshot: {shot}")


def fire(video):
    from playwright.sync_api import sync_playwright
    key = tab_key(video)
    st = load_state().get(key, {})
    if os.path.abspath(video) != st.get("video"):
        raise SystemExit("run 'prepare' for this exact file first (and get Ali's yes on the price)")
    ensure_chrome()
    with sync_playwright() as p:
        b, pg = page(p, key)
        price = fix_price(pg)
        if price is None or price > MAX_CREDITS:
            raise SystemExit(f"price is {price} credits (> {MAX_CREDITS}): not firing")
        if price != st.get("price"):
            raise SystemExit(f"price changed from {st.get('price')} to {price}: confirm with Ali again")
        known = set(pg.evaluate("() => [...document.querySelectorAll('video')].map(v => v.currentSrc)"))
        pg.locator("button:has-text('Upscale')").last.click()
        print(f"fired: {price} credits. waiting for the result (this can take several minutes)...")
        result = None
        end = time.time() + 30 * 60
        while time.time() < end and not result:
            time.sleep(10)
            srcs = pg.evaluate("() => [...document.querySelectorAll('video')].map(v => v.currentSrc)")
            new = [s for s in srcs if s and s not in known and s.startswith("http")]
            if new:
                result = new[0]
        if not result:
            raise SystemExit("no finished video showed up on the page in 30 min: check Higgsfield Assets by hand")
        base, _ = os.path.splitext(st["video"])
        out = base + " - 2k60.mp4"
        data = pg.request.get(result).body()
        open(out, "wb").write(data)
        print(f"downloaded: {out}  ({len(data) / 1e6:.1f} MB) from {result[:80]}")


def close():
    from playwright.sync_api import sync_playwright
    if not cdp_up():
        print("hidden Chrome is not running")
        return
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        b.new_browser_cdp_session().send("Browser.close")
    print("hidden Chrome closed")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("prepare", "fire", "close"):
        raise SystemExit(__doc__)
    if sys.argv[1] == "close":
        close()
    elif len(sys.argv) < 3:
        raise SystemExit(__doc__)
    elif sys.argv[1] == "prepare":
        prepare(sys.argv[2])
    else:
        fire(sys.argv[2])
