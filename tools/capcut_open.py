"""Open a CapCut project on Ali's screen so he can tweak it ("I want to tweak a few things").

    python tools/capcut_open.py "<CapCut project name>" ["<timeline name>"]

Makes the timeline the project's main one (the one CapCut shows first), moves the project to the
top of CapCut's home list, starts CapCut on Ali's normal desktop, opens the project and brings it
to the front. Needs CapCut closed first (a leftover hidden export instance is closed automatically).
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _wincap as wc  # noqa: E402
import capcut_draft as cd  # noqa: E402
import capcut_export as ce  # noqa: E402


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    project = sys.argv[1]
    timeline = sys.argv[2] if len(sys.argv) > 2 else None
    ce.ensure_closed()
    pdir = os.path.join(cd.DRAFT_ROOT, project)
    if not os.path.exists(pdir):
        raise SystemExit(f"no local CapCut project '{project}'")
    if timeline:
        proj_p = os.path.join(pdir, "Timelines", "project.json")
        proj = cd.load(proj_p)
        tid, _ = cd.find_timeline(pdir, timeline)
        proj["main_timeline_id"] = tid
        cd.dump(proj, proj_p)
        d = cd.load(os.path.join(pdir, "Timelines", tid, "draft_content.json"))
        cd.dump(d, os.path.join(pdir, "draft_content.json"))
        cd.bump_project(pdir, d["duration"])
    else:
        cd.bump_project(pdir, cd.load(os.path.join(pdir, "draft_content.json"))["duration"])
    env = dict(os.environ, QT_QPA_PLATFORM="windows:nowmpointer")  # posted click opens the project; normal mouse use unaffected
    subprocess.Popen([ce.EXE], cwd=os.path.dirname(ce.EXE), env=env)
    home = None
    for _ in range(120):
        time.sleep(0.5)
        big = [x for x in wc.capcut_windows() if x["rect"][2] - x["rect"][0] > 1000]
        if big:
            home = big[0]
            break
    if not home:
        raise SystemExit("CapCut did not start")
    time.sleep(4)
    wc.post_dblclick(home["hwnd"], *ce.HOME_FIRST_CARD)
    editor = None
    for _ in range(80):
        time.sleep(0.5)
        big = [x for x in wc.capcut_windows() if x["hwnd"] != home["hwnd"] and x["rect"][2] - x["rect"][0] > 1500]
        if big:
            editor = big[0]
            break
    if not editor:
        raise SystemExit("CapCut started but the project did not open; open it from the home screen")
    time.sleep(2)
    wc.restore_foreground(editor["hwnd"])
    print(f"opened '{project}'" + (f" on timeline '{timeline}'" if timeline else ""))


if __name__ == "__main__":
    main()
