"""Build a reel as a CapCut project AND export it with CapCut itself, invisibly.

    python tools/capcut_export.py <spec.json> [--open] [--no-build]

CapCut runs on a hidden Windows desktop (tools/_hiddendesk.py) with Qt's classic mouse input
(QT_QPA_PLATFORM=windows:nowmpointer), so posted clicks work and nothing appears on Ali's
screens. His cursor, keyboard and focus are never touched (Ali, 2026-10-08).
Flow: build the timeline (capcut_draft) -> registry export defaults (folder exports/_incoming,
1080P, 60 fps) -> launch CapCut hidden -> open the newest project -> Export -> 60fps -> Export ->
wait for the mp4 -> close CapCut -> move the file to exports/<mother>/<brand>/<page>/ -> LOG.csv.
Click map is for CapCut 9.5.0.4050 (see memory capcut-hidden-export). Never update CapCut.
"""
import csv
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import winreg

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _hiddendesk as hd  # noqa: E402
import _wincap as wc  # noqa: E402
import capcut_draft as cd  # noqa: E402

TESTED_VERSION = "9.5.0.4050"  # the click map below was measured on this CapCut version


def find_exe():
    apps = os.path.expandvars(r"%LOCALAPPDATA%\CapCut\Apps")
    vers = sorted((v for v in os.listdir(apps) if os.path.exists(os.path.join(apps, v, "CapCut.exe"))),
                  key=lambda v: [int(x) for x in v.split(".") if x.isdigit()]) if os.path.isdir(apps) else []
    if not vers:
        raise SystemExit(r"CapCut desktop not found in %LOCALAPPDATA%\CapCut\Apps")
    v = TESTED_VERSION if TESTED_VERSION in vers else vers[-1]
    if v != TESTED_VERSION:
        print(f"WARNING: CapCut {v} found, the export click map was measured on {TESTED_VERSION}. Re-check it on the first export.")
    return os.path.join(apps, v, "CapCut.exe")


EXE = find_exe()
INCOMING = os.path.join(cd.ECOM, "exports", "_incoming")
LOG = os.path.join(cd.ECOM, "exports", "LOG.csv")
REG = r"Software\Bytedance\CapCut\Modules\Export"

# window-local click points (CapCut 9.5.0.4050)
HOME_FIRST_CARD = (306, 784)
EDITOR_EXPORT_BTN = (1769, 17)
DLG_FPS_DROPDOWN = (575, 414)
POP_60FPS = (100, 233)
DLG_EXPORT_BTN = (588, 635)
DONE_CLOSE_BTN = (667, 605)
POPUP_SOUND_CANCEL = (266, 124)  # "Couldn't output sound" popup (320x150), Cancel button


def capcut_pids():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/FO", "CSV", "/NH"],
                         capture_output=True, text=True).stdout
    return [int(r[1]) for r in csv.reader(out.splitlines()) if len(r) > 1 and r[0] == "CapCut.exe"]


def kill_capcut():
    subprocess.run(["taskkill", "/IM", "CapCut.exe", "/T", "/F"], capture_output=True)
    for _ in range(20):
        if not capcut_pids():
            return
        time.sleep(0.5)


def ensure_closed():
    if not capcut_pids():
        return
    desk = hd.desktop()
    ours = [x for x in hd.windows(desk) if x["title"]]
    if wc.capcut_windows() and not ours:
        raise SystemExit("CapCut is open on your screen. Save and close it (tray too), then run again.")
    kill_capcut()  # a leftover hidden instance from an earlier export


def set_export_defaults():
    k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG)
    winreg.SetValueEx(k, "ExportPath", 0, winreg.REG_SZ, INCOMING.replace("\\", "/"))
    winreg.SetValueEx(k, "FrameRate", 0, winreg.REG_SZ, "60")
    winreg.SetValueEx(k, "Resolution", 0, winreg.REG_SZ, "1080P")
    winreg.CloseKey(k)


def wait_for(pred, desk, seconds):
    end = time.time() + seconds
    while time.time() < end:
        hit = [x for x in hd.windows(desk) if pred(x)]
        if hit:
            return hit[0]
        time.sleep(0.25)
    return None


def width(x):
    return x["rect"][2] - x["rect"][0]


def export_project(project_name, timeout=300):
    """Open the newest CapCut project on the hidden desktop and export it. Returns the mp4 path."""
    os.makedirs(INCOMING, exist_ok=True)
    set_export_defaults()
    env = dict(os.environ, QT_QPA_PLATFORM="windows:nowmpointer")
    _, desk = hd.launch(EXE, env=env)
    try:
        home = wait_for(lambda x: x["title"] == "CapCut" and width(x) > 1000, desk, 60)
        if not home:
            raise SystemExit("CapCut home screen did not appear")
        time.sleep(4)  # project cards load after the window
        # "Couldn't output sound" popup (Ali's PC volume is low/muted) blocks the home screen: press
        # Cancel. Never change his volume. (2026-10-09)
        for x in hd.windows(desk):
            r = x["rect"]
            if x["title"] == "CapCut" and x["hwnd"] != home["hwnd"] and 250 < r[2] - r[0] < 450 and r[3] - r[1] < 250:
                wc.post_click(x["hwnd"], *POPUP_SOUND_CANCEL)
                time.sleep(1)
        wc.post_dblclick(home["hwnd"], *HOME_FIRST_CARD)
        editor = wait_for(lambda x: x["title"] == "CapCut" and x["hwnd"] != home["hwnd"] and width(x) > 1500, desk, 40)
        if not editor:
            raise SystemExit("project did not open (first card on the home screen)")
        time.sleep(4)  # timeline + media load
        dlg = None
        for _ in range(3):
            wc.post_click(editor["hwnd"], *EDITOR_EXPORT_BTN)
            dlg = wait_for(lambda x: x["title"].startswith("Export-"), desk, 8)
            if dlg:
                break
        if not dlg:
            raise SystemExit("export dialog did not open")
        if dlg["title"] != f"Export-{project_name}":
            raise SystemExit(f"wrong project opened: {dlg['title']!r} (expected {project_name!r})")
        time.sleep(1)
        before = {x["hwnd"] for x in hd.windows(desk)}
        wc.post_click(dlg["hwnd"], *DLG_FPS_DROPDOWN)
        pop = wait_for(lambda x: x["hwnd"] not in before and width(x) == 328, desk, 5)
        if pop:
            wc.post_click(pop["hwnd"], *POP_60FPS)
            time.sleep(0.8)
        start = time.time()
        wc.post_click(dlg["hwnd"], *DLG_EXPORT_BTN)
        found, last = None, None
        while time.time() - start < timeout:
            time.sleep(1.5)
            new = [p for p in glob.glob(os.path.join(INCOMING, "*.mp4")) if os.path.getmtime(p) >= start - 1]
            if new:
                p = max(new, key=os.path.getmtime)
                size = os.path.getsize(p)
                if size and size == last:
                    found = p
                    break
                last = size
        if not found:
            raise SystemExit("export did not finish in time")
        time.sleep(1)
        done = [x for x in hd.windows(desk) if x["title"].startswith("Export-")]
        if done:
            wc.post_click(done[0]["hwnd"], *DONE_CLOSE_BTN)
        return found
    finally:
        time.sleep(1)
        kill_capcut()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit(__doc__)
    spec_path = args[0]
    raw = cd.load(spec_path)
    spec = cd.expand_spec(raw)
    ensure_closed()
    if "--no-build" not in sys.argv:
        d, tname, report = cd.build_content(spec)
        print(f"template: {tname}  ->  {d['duration'] / cd.US:.2f}s")
        print("\n".join("  " + r for r in report if not r.startswith(("video ", "audio "))))
        print("project:", cd.add_timeline(spec, d) if spec.get("into_draft") else cd.write_draft(spec, d))
    project = spec.get("into_draft") or spec.get("draft_name")
    t0 = time.time()
    mp4 = export_project(project)
    prof = cd.load_profile(spec["brand"]) if spec.get("brand") else {}
    page = spec.get("page", "us")
    dest_dir = os.path.join(cd.ECOM, (prof.get("export_dir") or "exports/other/<page>").replace("<page>", page))
    os.makedirs(dest_dir, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d_%H%M")
    hook = os.path.splitext(os.path.basename(raw.get("hook", "template-hook")))[0].replace("-FINAL", "")
    song = (raw.get("song") or spec["template"]["timeline"]).split("/")[-1]
    style = raw.get("caption_style", "custom")
    final = os.path.join(dest_dir, f"{stamp} {hook} - {song} - {style}.mp4")
    shutil.move(mp4, final)
    new_log = not os.path.exists(LOG)
    with open(LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new_log:
            w.writerow(["exported_at", "brand", "page", "file", "capcut_project", "timeline", "hook", "song",
                        "caption_style", "spec", "posted"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M"), spec.get("brand", ""), page,
                    os.path.relpath(final, cd.ECOM).replace("\\", "/"), project, spec.get("timeline_name", ""),
                    raw.get("hook", ""), song, style, os.path.relpath(os.path.abspath(spec_path), cd.ECOM).replace("\\", "/"), ""])
    probe = cd.probe(final)
    print(f"exported by CapCut in {time.time() - t0:.0f}s: {final}  ({probe[1]}x{probe[2]}, {probe[0] / cd.US:.2f}s)")
    if "--open" in sys.argv:
        os.startfile(final)


if __name__ == "__main__":
    main()
