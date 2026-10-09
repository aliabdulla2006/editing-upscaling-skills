"""Per-brand song library, mined from Ali's own CapCut projects.

Every reel Ali edits in CapCut has a song "bed" (a section of the track, ~10-15 s) and,
for music-box brands, a ~4 s "end sound" under the fridge shot (the box playing that song).
This script scans every CapCut project, records which song sections each brand uses,
copies the audio into music/<brand>/ (gitignored), and writes music/library.json.

    python tools/song_library.py scan      # rebuild music/library.json + music/README.md
    python tools/song_library.py list <brand>
    python tools/song_library.py learn <CapCut draft name|dir> <timeline>   # after Ali fixes a timeline by hand

Songs with an end sound are placed by "handoff" (where the song is cut and the raw box audio
takes over); a longer slot starts the song earlier. Manual edits to "title", "start", "handoff", "end_sound" or "notes" in library.json survive a rescan
(entries are matched by id). Add "pinned": true to keep a song a rescan no longer finds.
"""
import collections
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from capcut_draft import DRAFT_ROOT, ECOM, US, classify_audio, load  # noqa: E402

LIB = os.path.join(ECOM, "music", "library.json")
README = os.path.join(ECOM, "music", "README.md")

# CapCut project folder name (prefix match) -> brand slug. None = skip.
PROJECT_BRANDS = [
    ("Celine Dion", "celine-dion"),
    ("Noah Kahan", "noah-kahan"),
    ("Car Door Projector", "car-door-projector"),
    ("0918", "music-box-golden-age"),
    ("Olivia Rodrigo", None),  # livies-vinyl stopped 2026-10-04
]
PROJECTS_JSON = os.path.join(ECOM, "music", "projects.json")
if os.path.exists(PROJECTS_JSON):  # editable mapping, no code change needed (CapCut project name prefix -> brand / null)
    PROJECT_BRANDS = [(k, v) for k, v in json.load(open(PROJECTS_JSON, encoding="utf-8")).items() if not k.startswith("_")]
KEEP = ("title", "start", "handoff", "end_sound", "notes", "pinned", "learned_from")


def brand_of(project):
    for prefix, brand in PROJECT_BRANDS:
        if project.startswith(prefix):
            return brand
    return None


def project_dirs():
    for base in (DRAFT_ROOT, *[os.path.join(DRAFT_ROOT, d) for d in os.listdir(DRAFT_ROOT) if d.startswith(".cloud_cache")]):
        for name in os.listdir(base):
            p = os.path.join(base, name)
            if os.path.isdir(p) and not name.startswith(".") and os.path.exists(os.path.join(p, "Timelines", "project.json")):
                yield name, p


def audio_file(project_dir, path):
    base = os.path.basename(path)
    for cand in (path, os.path.join(project_dir, "materials", "audio", base)):
        if cand and not cand.startswith("##") and os.path.exists(cand):
            return cand
    return None


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def clean_title(fname):
    t = os.path.splitext(fname)[0]
    t = re.sub(r"\((mp3\.pm|Official[^)]*|Vid[ée]o[^)]*|vqMusic)\)", "", t, flags=re.I)
    t = re.sub(r"_?\(mp3\.pm\)|vqMusic|[ _](19|20)\d\d$", "", t)
    t = t.replace("_", " ")
    t = re.sub(r"^.*? - ", "", t) if " - " in t else t  # drop "Artist - "
    return re.sub(r"\s+", " ", t).strip(" -") or fname


def scan():
    uses = collections.defaultdict(list)  # (brand, bed file basename) -> [use]
    for pname, pdir in project_dirs():
        brand = brand_of(pname)
        if not brand:
            continue
        proj = load(os.path.join(pdir, "Timelines", "project.json"))
        for t in proj["timelines"]:
            f = os.path.join(pdir, "Timelines", t["id"], "draft_content.json")
            if t.get("is_marked_delete") or not os.path.exists(f):
                continue
            d = load(f)
            bed, end = classify_audio(d)
            if not bed:
                continue
            bed_src = audio_file(pdir, bed["path"])
            if not bed_src:
                continue
            use = {"project": pname, "timeline": t["name"], "start": round(bed["start"] / US, 2),
                   "length": round(bed["length"] / US, 2), "updated": t.get("update_time", 0),
                   "bed_src": bed_src}
            if end:
                use["end_src"] = audio_file(pdir, end["path"])
                use["end_start"] = round(end["start"] / US, 2)
                use["handoff"] = round(bed["handoff"] / US, 2)
            uses[(brand, os.path.basename(bed_src))].append(use)

    old = load(LIB) if os.path.exists(LIB) else {}
    lib = {}
    for (brand, bed_name), us in sorted(uses.items()):
        mdir = os.path.join(ECOM, "music", brand)
        os.makedirs(mdir, exist_ok=True)

        def copy_in(src):
            dst = os.path.join(mdir, os.path.basename(src))
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
            return os.path.relpath(dst, ECOM).replace("\\", "/")

        # Ali's most recently edited timeline wins (copied projects make vote counts meaningless).
        latest = max(us, key=lambda u: u["updated"])
        starts = {round(u["start"], 1) for u in us}
        with_end = [u for u in us if u.get("end_src")]
        end, handoff = None, None
        if with_end:
            e = max(with_end, key=lambda u: u["updated"])
            end = {"file": copy_in(e["end_src"]), "start": e["end_start"]}
            handoff = e["handoff"]  # paired with that end sound: the song is cut here, the raw box audio takes over
        title = clean_title(bed_name)
        if any(len(w) > 25 for w in title.split()):  # unreadable download name: use Ali's timeline name
            title = re.sub(r"\s*\d+$", "", latest["timeline"]).strip()
        sid = slug(title)[:40].strip("-")
        entry = {
            "id": sid, "title": title, "file": copy_in(latest["bed_src"]),
            "handoff": handoff, "start": latest["start"], "typical_length": latest["length"], "end_sound": end,
            "other_starts": sorted(s for s in starts if s != round(latest["start"], 1)),
            "used_in": sorted({f"{u['project']} / {u['timeline']}" for u in us}),
        }
        prev = next((s for s in old.get(brand, []) if s["id"] == sid), None)
        if prev:
            entry.update({k: prev[k] for k in KEEP if k in prev})
        lib.setdefault(brand, []).append(entry)
    for brand, songs in old.items():  # keep pinned songs the scan no longer finds
        ids = {s["id"] for s in lib.get(brand, [])}
        lib.setdefault(brand, []).extend(s for s in songs if s.get("pinned") and s["id"] not in ids)

    with open(LIB, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)
    write_readme(lib)
    for brand, songs in lib.items():
        print(f"{brand}: {len(songs)} songs")


def fmt(sec):
    return f"{int(sec // 60)}:{sec % 60:04.1f}"


def write_readme(lib):
    lines = ["# Song library", "",
             "Built by `python tools/song_library.py scan` from Ali's CapCut projects. Source of truth: `library.json`.",
             "Audio files live next to this file per brand and are gitignored.", ""]
    for brand, songs in lib.items():
        lines += [f"## {brand}", "", "| id | Song | Song hands off at | Section starts at (last edit) | End sound |", "|---|---|---|---|---|"]
        for s in songs:
            e = f"{os.path.basename(s['end_sound']['file'])} @ {s['end_sound']['start']}s" if s.get("end_sound") else "none"
            h = fmt(s['handoff']) if s.get('handoff') is not None else 'n/a (no end sound)'
            lines.append(f"| `{s['id']}` | {s['title']} | {h} | {fmt(s['start'])} | {e} |")
        lines.append("")
    with open(README, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def learn(draft, timeline):
    """Ali fixed a generated timeline by hand in CapCut: copy his song handoff, end sound start
    and end-sound mix level back into the library so every later build uses them."""
    from capcut_draft import MIX, db, find_timeline, section_loudness
    pdir = draft if os.path.isdir(draft) else os.path.join(DRAFT_ROOT, draft)
    tid, tname = find_timeline(pdir, timeline)
    d = load(os.path.join(pdir, "Timelines", tid, "draft_content.json"))
    bed, end = classify_audio(d)
    lib = load(LIB)
    hit = [(b, s) for b, songs in lib.items() for s in songs if os.path.basename(s["file"]) == bed["file"]]
    if not hit:
        raise SystemExit(f"song file {bed['file']} is not in music/library.json")
    brand, song = hit[0]
    src = f"{os.path.basename(pdir)} / {tname}"
    old_h = song.get("handoff")
    song["handoff"] = round(bed["handoff"] / US, 3)
    song["start"] = round(bed["start"] / US, 3)
    print(f"{brand}/{song['id']}: handoff {old_h} -> {song['handoff']}")
    if end:
        song["end_sound"] = {"file": song["end_sound"]["file"] if song.get("end_sound") and
                             os.path.basename(song["end_sound"]["file"]) == end["file"] else
                             f"music/{brand}/{end['file']}", "start": round(end["start"] / US, 3)}
        bed_lufs, bed_segs = section_loudness(d, bed["file"])
        end_lufs, end_segs = section_loudness(d, end["file"])
        below = round((bed_lufs + db(bed_segs[0]["volume"])) - (end_lufs + db(end_segs[0]["volume"])), 1)
        mix = load(MIX) if os.path.exists(MIX) else {}
        mix.setdefault("default", {})
        mix.setdefault(brand, {})
        mix[brand].update(end_sound_db_below_song=below, learned_from=src)
        if "end_sound_db_below_song" not in mix["default"]:
            mix["default"].update(end_sound_db_below_song=below, learned_from=src)
        with open(MIX, "w", encoding="utf-8") as f:
            json.dump(mix, f, ensure_ascii=False, indent=2)
        print(f"{brand}: end sound plays {below} dB under the song (heard loudness)")
    song.setdefault("notes", "")
    song["learned_from"] = src
    with open(LIB, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)
    write_readme(lib)


def get_song(ref):
    """'brand/id' -> library entry."""
    brand, sid = ref.split("/", 1)
    for s in load(LIB).get(brand, []):
        if s["id"] == sid:
            return s
    raise SystemExit(f"song '{ref}' not in music/library.json")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "scan":
        scan()
    elif len(sys.argv) >= 4 and sys.argv[1] == "learn":
        learn(sys.argv[2], sys.argv[3])
    elif len(sys.argv) >= 3 and sys.argv[1] == "list":
        for s in load(LIB).get(sys.argv[2], []):
            print(f"{s['id']:32} {s['title']:40} from {fmt(s['start'])}  end_sound={'yes' if s.get('end_sound') else 'no'}")
    else:
        raise SystemExit(__doc__)
