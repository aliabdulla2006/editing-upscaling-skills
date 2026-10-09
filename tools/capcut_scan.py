"""List every CapCut project + timeline with what the editing skill needs to turn it into a template.

    python tools/capcut_scan.py                 # all projects (local + cloud-synced)
    python tools/capcut_scan.py "<project>"     # one project, with every clip / caption / audio piece

Per timeline: length, hook (clip at 0:00, pieces, speed, volume), song section (start -> handoff), raw end
sound, captions in order. "template OK" = the hook is on the top video track at 0:00 and the timeline has a song.
Read-only: never writes to CapCut.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import capcut_draft as cd  # noqa: E402


def fmt(us):
    s = us / cd.US
    return "%d:%05.2f" % (s // 60, s % 60)


def projects():
    roots = [cd.DRAFT_ROOT] + [os.path.join(cd.DRAFT_ROOT, x) for x in os.listdir(cd.DRAFT_ROOT) if x.startswith(".cloud_cache")]
    for r in roots:
        for name in sorted(os.listdir(r)):
            p = os.path.join(r, name)
            if not name.startswith(".") and os.path.exists(os.path.join(p, "Timelines", "project.json")):
                yield name, p, "cloud" if ".cloud_cache" in r else "local"


def show(name, pdir, kind, detail=False):
    print(f"\n######## {name}   ({kind})")
    for t in cd.load(os.path.join(pdir, "Timelines", "project.json"))["timelines"]:
        f = os.path.join(pdir, "Timelines", t["id"], "draft_content.json")
        if t.get("is_marked_delete") or not os.path.exists(f):
            continue
        d = cd.load(f)
        sl = cd.slot_segments(d)
        bed, end = cd.classify_audio(d)
        tm = {x["id"]: json.loads(x["content"])["text"] for x in d["materials"]["texts"]}
        caps = sorted((s for tr in d["tracks"] if tr["type"] == "text" for s in tr["segments"]),
                      key=lambda s: s["target_timerange"]["start"])
        hook = sl.get("hook")
        ok = bool(hook) and bool(bed)
        print(f"\n== {t['name']}   {d['duration'] / cd.US:.2f}s   {'template OK' if ok else 'NOT a template (' + ('no hook at 0:00' if not hook else 'no song') + ')'}")
        if hook:
            print(f"   hook : {os.path.basename(cd.path_of(d, hook))}  {hook['target_timerange']['duration'] / cd.US:.2f}s "
                  f"x{hook.get('speed', 1):.2f} vol {hook['volume']:.2f}  pieces {len(sl['hook_pieces'])}")
        if bed:
            print(f"   song : {bed['file']}  {fmt(bed['start'])} -> {fmt(bed['handoff'])}")
        print(f"   end sound: {end['file'] + ' from ' + fmt(end['start']) if end else 'none'}")
        for s in caps:
            st = s["target_timerange"]["start"]
            print(f"   caption {st / cd.US:5.2f}-{(st + s['target_timerange']['duration']) / cd.US:5.2f}  {tm.get(s['material_id'], '?')!r}")
        if detail:
            vm = {v["id"]: os.path.basename(v["path"]) for v in d["materials"]["videos"]}
            for i, tr in enumerate(d["tracks"]):
                if tr["type"] != "video":
                    continue
                for s in sorted(tr["segments"], key=lambda s: s["target_timerange"]["start"]):
                    st = s["target_timerange"]["start"]
                    print(f"   V{i} {st / cd.US:5.2f}-{(st + s['target_timerange']['duration']) / cd.US:5.2f} "
                          f"{vm.get(s['material_id'], '?')[:50]}  x{s.get('speed', 1):.2f} vol {s['volume']:.2f}")


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    for name, pdir, kind in projects():
        if only and name != only:
            continue
        show(name, pdir, kind, detail=bool(only))
