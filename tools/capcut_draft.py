"""Build a CapCut desktop draft from one of Ali's real reel timelines used as a template.

The template timeline keeps every edit decision Ali made (cuts, speeds, volumes,
caption font/stroke/position). The spec only swaps what changes per video:
media files (hook, rehook, song, fridge sound), song section start, caption text.

Usage:
    python tools/capcut_draft.py build <spec.json> [--dry-run]
    python tools/capcut_draft.py timelines <capcut project dir>

Spec (paths relative to the ecom root are fine):
{
  "draft_name": "AUTO Celine DE test",
  "template": {"project_dir": "<CapCut project folder>", "timeline": "V1 My Heart Will Go On"},
  "media_dirs": ["products/celine-dion", "music/celine-dion"],
  "replace_media": {
     "<basename in template>": {"path": "<new file>", "source_start": 39.83}
  },
  "texts": ["new caption 1", null, "new caption 3"]   # in timeline order, null = keep
}
Shortcuts: "hook": "<file>" / "rehook": "<file>" swap the 1st / 2nd distinct clip in the template;
"song": "<brand>/<song id>" swaps the song bed + its end sound from music/library.json.
Add "into_draft": "<existing local draft name>" + "timeline_name" to add a new timeline tab
to that project instead of creating a new project.

CapCut must be closed while writing (it rewrites root_meta_info.json on exit).
Pinned to CapCut desktop 9.5 (draft new_version 187.0.0). Do not let CapCut update.
"""
import collections
import copy
import json
import math
import os
import shutil
import subprocess
import sys
import time
import uuid

ECOM = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRAFT_ROOT = os.path.join(os.environ["LOCALAPPDATA"], "CapCut", "User Data", "Projects", "com.lveditor.draft")


def find_skeleton():
    """An empty local project made by CapCut itself, used as the folder skeleton for new projects.
    Override with env CAPCUT_SKELETON. On a new PC: open CapCut once, create an empty project, close."""
    if os.environ.get("CAPCUT_SKELETON"):
        return os.path.join(DRAFT_ROOT, os.environ["CAPCUT_SKELETON"])
    if not os.path.isdir(DRAFT_ROOT):
        return None
    cands = []
    for name in os.listdir(DRAFT_ROOT):
        d = os.path.join(DRAFT_ROOT, name)
        if name.startswith((".", "AUTO ")) or not os.path.exists(os.path.join(d, "Timelines", "project.json"))                 or not os.path.exists(os.path.join(d, "draft_meta_info.json")):
            continue
        cands.append((os.path.getsize(os.path.join(d, "draft_content.json")) if os.path.exists(os.path.join(d, "draft_content.json")) else 1e12, d))
    return min(cands)[1] if cands else None


SKELETON = find_skeleton()
BACKUP_DIR = os.path.join(ECOM, "tools", "_capcut_backups")
US = 1_000_000  # CapCut stores time in microseconds


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def dump(obj, p):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def fwd(p):
    return os.path.abspath(p).replace("\\", "/")


def resolve(p):
    return p if os.path.isabs(p) else os.path.join(ECOM, p)


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
         "-of", "json", path], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    v = next((s for s in j.get("streams", []) if s.get("codec_type") == "video"), {})
    return int(float(j["format"]["duration"]) * US), v.get("width"), v.get("height")


def _iir(x, b, a):
    y, x1, x2, y1, y2 = [0.0] * len(x), 0.0, 0.0, 0.0, 0.0
    b0, b1, b2, a1, a2 = b[0], b[1], b[2], a[1], a[2]
    for i, v in enumerate(x):
        o = b0 * v + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, v, y1, o
        y[i] = o
    return y


def loudness(path, start_us, dur_us):
    """Integrated loudness (LUFS, ITU BS.1770 / EBU R128, same as ffmpeg ebur128) of a file section.
    Pure PyAV + numpy because ffmpeg.exe is blocked by Windows Application Control on this PC."""
    import av
    import numpy as np
    rate = 48000
    with av.open(path) as f:
        if not f.streams.audio:
            return None  # silent clip
        st = f.streams.audio[0]
        f.seek(int(start_us / US / st.time_base), stream=st)
        rs = av.AudioResampler(format="fltp", layout="stereo", rate=rate)
        chunks, t_end = [], (start_us + dur_us) / US
        for frame in f.decode(st):
            ft = float(frame.pts * st.time_base) if frame.pts is not None else 0.0
            if ft > t_end:
                break
            for rf in rs.resample(frame):
                chunks.append((float(rf.pts) / rate if rf.pts is not None else ft, rf.to_ndarray()))
    if not chunks:
        return None
    pcm = np.concatenate([c for _, c in chunks], axis=1)
    t0 = chunks[0][0]
    a = max(0, int(round((start_us / US - t0) * rate)))
    pcm = pcm[:, a:a + int(dur_us / US * rate)]
    power = np.zeros(pcm.shape[1])
    for ch in pcm:  # K-weighting: high shelf + high pass (48 kHz coefficients)
        k = _iir(_iir(ch.tolist(), (1.53512485958697, -2.69169618940638, 1.19839281085285),
                      (1.0, -1.69065929318241, 0.73248077421585)),
                 (1.0, -2.0, 1.0), (1.0, -1.99004745483398, 0.99007225036621))
        power += np.square(np.asarray(k))
    blk, hop = int(0.4 * rate), int(0.1 * rate)
    if len(power) < blk:
        return None
    cs = np.concatenate([[0.0], np.cumsum(power)])
    ms = np.array([(cs[i + blk] - cs[i]) / blk for i in range(0, len(power) - blk + 1, hop)])
    lk = -0.691 + 10 * np.log10(np.maximum(ms, 1e-12))
    gated = ms[lk > -70]
    if not len(gated):
        return None
    rel = -0.691 + 10 * np.log10(gated.mean()) - 10
    gated = ms[(lk > -70) & (lk > rel)]
    return float(-0.691 + 10 * np.log10(gated.mean()))


def db(v):
    return 20 * math.log10(max(v, 1e-6))


def capcut_running():
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe"], capture_output=True, text=True).stdout
    return "CapCut.exe" in out


def utf16len(s):
    return len(s.encode("utf-16-le")) // 2


def split_trailing_emoji(text):
    """Return index where the trailing emoji run (plus its leading space) starts."""
    i = len(text)
    while i > 0 and (ord(text[i - 1]) > 0x2000 and not text[i - 1].isalpha() or text[i - 1] in "️‍"):
        i -= 1
    if i < len(text) and i > 0 and text[i - 1] == " ":
        i -= 1
    return i


def set_text(material, new_text):
    c = json.loads(material["content"])
    styles = c["styles"]
    base, emoji = styles[0], styles[-1]
    cut = split_trailing_emoji(new_text)
    head, tail = new_text[:cut], new_text[cut:]
    new_styles = [dict(copy.deepcopy(base), range=[0, utf16len(head)])]
    if tail and len(styles) > 1:
        new_styles.append(dict(copy.deepcopy(emoji), range=[utf16len(head), utf16len(new_text)]))
    elif tail:
        new_styles[0]["range"] = [0, utf16len(new_text)]
    c["text"], c["styles"] = new_text, new_styles
    material["content"] = json.dumps(c, ensure_ascii=False, separators=(",", ":"))


def classify_audio(d):
    """Split a timeline's audio into the song bed (longest audio material) and the short end sound
    under the last clip (music-box brands: the box playing the song under the fridge shot)."""
    mats = {m["id"]: m for m in d["materials"]["audios"]}
    by_file = collections.defaultdict(list)  # one song can sit in several materials / pieces
    for t in d["tracks"]:
        if t["type"] == "audio":
            for s in t["segments"]:
                if s["material_id"] in mats and s.get("source_timerange"):
                    by_file[os.path.basename(mats[s["material_id"]]["path"])].append(s)
    info = []
    for name, segs in by_file.items():
        first = min(segs, key=lambda s: s["target_timerange"]["start"])
        last = max(segs, key=lambda s: s["target_timerange"]["start"])
        info.append({"file": name, "path": mats[first["material_id"]]["path"],
                     "start": first["source_timerange"]["start"], "at": first["target_timerange"]["start"],
                     # source time where the song is cut = where the end sound (raw box audio) takes over
                     "handoff": last["source_timerange"]["start"] + last["source_timerange"]["duration"],
                     "length": sum(s["target_timerange"]["duration"] for s in segs)})
    late = lambda a: a["at"] >= 0.5 * d["duration"] and a["length"] <= 6 * US  # noqa: E731
    beds = [a for a in info if a["length"] >= 5 * US and not late(a)]
    bed = max(beds, key=lambda a: a["length"]) if beds else None
    ends = [a for a in info if a is not bed and late(a)]
    return bed, (max(ends, key=lambda a: a["at"]) if ends else None)


MIX = os.path.join(ECOM, "music", "mix.json")


def mix_settings(brand):
    m = load(MIX) if os.path.exists(MIX) else {}
    return {**m.get("default", {}), **m.get(brand, {})}


def section_loudness(d, file_name):
    """(LUFS of the file over the section the timeline plays, timeline volume of that piece)."""
    mats = {m["id"]: m for m in d["materials"]["audios"]}
    segs = [s for t in d["tracks"] if t["type"] == "audio" for s in t["segments"]
            if s["material_id"] in mats and os.path.basename(mats[s["material_id"]]["path"]) == file_name]
    start = min(s["source_timerange"]["start"] for s in segs)
    end = max(s["source_timerange"]["start"] + s["source_timerange"]["duration"] for s in segs)
    path = mats[segs[0]["material_id"]]["path"]
    return loudness(path, start, end - start), segs


def set_end_sound_volume(d, brand):
    """Raw box audio under the fridge sounds filmed on an iPhone from a distance: it plays a fixed
    number of dB under the song bed, measured as heard (file loudness + timeline gain).
    Learned from Ali's Timeline 03 fix, 2026-10-07: 10.9 dB under."""
    below = mix_settings(brand).get("end_sound_db_below_song")
    bed, end = classify_audio(d)
    if below is None or not bed or not end:
        return []
    bed_lufs, bed_segs = section_loudness(d, bed["file"])
    end_lufs, end_segs = section_loudness(d, end["file"])
    if bed_lufs is None or end_lufs is None:
        return [f"WARN could not measure loudness, end sound volume left as template"]
    bed_heard = bed_lufs + db(bed_segs[0]["volume"])
    vol = 10 ** ((bed_heard - below - end_lufs) / 20)
    for s in end_segs:
        s["volume"] = vol
    return [f"mix   end sound volume {vol:.2f} ({below} dB under the song: song {bed_heard:.1f}, raw {bed_heard - below:.1f} LUFS heard)"]


FRAME = US // 30


def slot_segments(d):
    """{'hook': seg, 'rehook': seg} on the topmost video track that has a clip at 0:00."""
    vtracks = [t for t in d["tracks"] if t["type"] == "video" and t["segments"]]
    at0 = [t for t in vtracks if min(s["target_timerange"]["start"] for s in t["segments"]) < FRAME]
    if not at0:
        return {}
    segs = sorted(at0[-1]["segments"], key=lambda s: s["target_timerange"]["start"])
    hook = segs[0]
    name = os.path.basename(path_of(d, hook))
    pieces = [hook]
    for s in segs[1:]:
        if os.path.basename(path_of(d, s)) != name:
            break
        pieces.append(s)
    out = {"hook": hook, "hook_pieces": pieces, "track": at0[-1]}
    nxt = [s for s in segs[1:] if os.path.basename(path_of(d, s)) != os.path.basename(path_of(d, hook))]
    if nxt:
        out["rehook"] = nxt[0]
    return out


def path_of(d, seg):
    for k in ("videos", "audios"):
        for m in d["materials"][k]:
            if m["id"] == seg["material_id"]:
                return m["path"]
    return ""


def set_speed(d, seg, speed):
    seg["speed"] = speed
    for m in d["materials"].get("speeds", []):
        if m["id"] in seg.get("extra_material_refs", []):
            m["speed"], m["mode"], m["curve_speed"] = speed, 0, None


def ripple_slot(d, seg, src_in, src_dur, speed=1.0, anchor="start"):
    """Give `seg` a new source range (played at `speed`, default normal speed like a fresh clip
    dropped into CapCut) and ripple the rest of the timeline. Returns the time shift."""
    set_speed(d, seg, speed)
    t0, old = seg["target_timerange"]["start"], seg["target_timerange"]["duration"]
    new = int(round(src_dur / speed))
    delta, cut = new - old, t0 + old
    seg["source_timerange"] = {"start": src_in, "duration": src_dur}
    seg["target_timerange"]["duration"] = new
    if delta == 0:
        return 0
    bed, end = classify_audio(d)
    anchor = anchor or "start"
    ends_video = cut >= d["duration"] - FRAME  # the slot is the last clip (e.g. one full-video clip)
    for t in d["tracks"]:
        for s in t["segments"]:
            if s is seg:
                continue
            tr = s["target_timerange"]
            st, en = tr["start"], tr["start"] + tr["duration"]
            if ends_video and t["type"] == "text":
                # CTA keeps its length and stays on the last seconds; the opening caption absorbs the change
                if en >= cut - FRAME and st > FRAME:
                    tr["start"] += delta
                elif st < FRAME:
                    tr["duration"] += delta
                if tr["duration"] <= 0:
                    raise SystemExit("new clip is too short for this template (a caption would vanish)")
                continue
            if st >= cut - FRAME:                     # after the cut: move
                tr["start"] += delta
            elif en >= cut - FRAME:                   # spans (or ends at) the cut: stretch
                if t["type"] == "video":
                    continue                          # overlay clip under the hook: leave it
                tr["duration"] += delta
                sr = s.get("source_timerange")
                if t["type"] == "audio" and sr:
                    sp = s.get("speed") or 1.0
                    ds = int(round(delta * sp))
                    sr["duration"] += ds
                    is_bed = bed and os.path.basename(path_of(d, s)) == bed["file"]
                    if is_bed and (end or anchor == "end"):  # keep the handoff / the song's end fixed
                        sr["start"] -= ds
                        if sr["start"] < 0:
                            raise SystemExit("hook is too long: the song would start before 0:00")
            if tr["duration"] <= 0:
                raise SystemExit("new clip is too short for this template (a caption or sound would vanish)")
    d["duration"] += delta
    return delta


def drop_clip(d, basename):
    """Remove every video clip of file `basename` from the timeline and close the gap: later clips,
    captions and sounds move left; captions and the song that span the cut get shorter (the song keeps
    its start, so it ends earlier). Spec key "drop_clips": ["checkout-pay.mp4"] (Ali 2026-10-09:
    unboxing hooks don't need the store checkout shot)."""
    report = []
    for t in [t for t in d["tracks"] if t["type"] == "video"]:
        for seg in sorted([s for s in t["segments"] if os.path.basename(path_of(d, s)) == basename],
                          key=lambda s: -s["target_timerange"]["start"]):
            t0, dur = seg["target_timerange"]["start"], seg["target_timerange"]["duration"]
            t["segments"].remove(seg)
            cut = t0 + dur
            for tt in d["tracks"]:
                for s in tt["segments"]:
                    tr = s["target_timerange"]
                    st, en = tr["start"], tr["start"] + tr["duration"]
                    if st >= cut - FRAME:
                        tr["start"] -= dur
                    elif en > t0 + FRAME:            # spans the removed clip: shorten
                        if tt["type"] == "video":
                            continue
                        tr["duration"] -= dur
                        sr = s.get("source_timerange")
                        if tt["type"] == "audio" and sr:
                            sr["duration"] -= int(round(dur * (s.get("speed") or 1.0)))
                        if tr["duration"] <= 0:
                            raise SystemExit(f"dropping {basename} would make a caption or sound vanish")
            d["duration"] -= dur
            report.append(f"drop  {basename} ({dur / US:.2f}s, rest of the timeline moved up)")
    if not report:
        raise SystemExit(f"drop_clips: no clip named {basename} in this template")
    return report


def style_text(d, role, st, extras=()):
    """Retime / move / resize a caption by role ("hook" = longest caption at 0:00, "cta" = last one).
    st keys: "start" (seconds; the caption still ends where it did), "y" (CapCut y, +1 = top edge),
    "y_shift" (added to y), "scale_mult" (multiplies the caption's scale)."""
    texts = {m["id"]: m for m in d["materials"]["texts"]}
    tsegs = sorted((s for t in d["tracks"] if t["type"] == "text" for s in t["segments"]),
                   key=lambda s: s["target_timerange"]["start"])
    if role == "hook":
        at0 = [s for s in tsegs if s["target_timerange"]["start"] < FRAME]
        seg = max(at0, key=lambda s: s["target_timerange"]["duration"]) if at0 else None
    else:
        body = [s for s in tsegs if json.loads(texts[s["material_id"]]["content"])["text"] not in set(extras)]
        seg = body[-1] if body else None
    if seg is None:
        raise SystemExit(f"text_style: template has no '{role}' caption")
    out, tr, clip = [], seg["target_timerange"], seg.setdefault("clip", {})
    if st.get("start") is not None:
        new = int(round(st["start"] * US))
        end = tr["start"] + tr["duration"]
        if new >= end - FRAME:
            raise SystemExit(f"text_style: {role} caption would start after it ends")
        tr["start"], tr["duration"] = new, end - new
        out.append(f"start {st['start']:.2f}s")
    tf = clip.setdefault("transform", {"x": 0.0, "y": 0.0})
    if st.get("y") is not None:
        tf["y"] = float(st["y"])
    if st.get("y_shift"):
        tf["y"] = tf.get("y", 0.0) + float(st["y_shift"])
    if st.get("y") is not None or st.get("y_shift"):
        out.append(f"y {tf['y']:.3f}")
    if st.get("scale_mult"):
        sc = clip.setdefault("scale", {"x": 1.0, "y": 1.0})
        sc["x"] *= float(st["scale_mult"])
        sc["y"] *= float(st["scale_mult"])
        out.append(f"scale {sc['x']:.3f}")
    return [f"style {role} caption: " + ", ".join(out)]


def locate_media(name, dirs, project_dir, assets_dir):
    """Find a template clip on disk: repo media_dirs, then without CapCut's UUID_ prefix, then the
    copy inside CapCut's own project folder (copied into <product>/edit-assets/ so it stays put)."""
    import re
    hit = find_media(name, dirs)
    bare = re.sub(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f-]{27}_", "", name)
    if not hit and bare != name:
        hit = find_media(bare, dirs)
    if hit:
        return hit
    for sub in ("video", "audio", "image"):
        src = os.path.join(project_dir, "materials", sub, name)
        if os.path.exists(src):
            if not assets_dir:
                return src
            dst_dir = resolve(assets_dir)
            os.makedirs(dst_dir, exist_ok=True)
            dst = os.path.join(dst_dir, bare)
            if not os.path.exists(dst):
                shutil.copy2(src, dst)
            return dst
    return None


def set_hook_volume(d, spec):
    """The hook person's lines must be heard over the song. Ali's talking-hook mixes put the hook
    ~3 dB above the song (hook clip boosted to ~3x). Measured per clip; "hook_volume" overrides."""
    seg = slot_segments(d)["hook"]
    if spec.get("hook_volume") is None and seg.get("volume", 1.0) < 0.05:
        return ["mix   hook stays muted (muted in Ali's template)"]
    if spec.get("hook_volume") is not None:
        seg["volume"] = float(spec["hook_volume"])
        return [f"mix   hook volume {seg['volume']:.2f} (set by spec)"]
    over = mix_settings(spec.get("brand", "")).get("hook_db_over_song", 3.0)
    bed, _ = classify_audio(d)
    if not bed:
        return []
    am = {a["id"]: a for a in d["materials"]["audios"]}
    under = [s for t in d["tracks"] if t["type"] == "audio" for s in t["segments"]
             if s["material_id"] in am and os.path.basename(am[s["material_id"]]["path"]) == bed["file"]]
    first = min(under, key=lambda s: s["target_timerange"]["start"])
    dur = min(seg["target_timerange"]["duration"], first["target_timerange"]["duration"])
    hook_l = loudness(path_of(d, seg), seg["source_timerange"]["start"], seg["source_timerange"]["duration"])
    song_l = loudness(am[first["material_id"]]["path"], first["source_timerange"]["start"], dur)
    if hook_l is None:
        return ["mix   hook clip has no sound, volume left as template"]
    if song_l is None:
        return ["WARN could not measure the song, hook volume left as template"]
    vol = 10 ** ((song_l + db(first["volume"]) + over - hook_l) / 20)
    vol = max(0.5, min(vol, 6.0))
    seg["volume"] = vol
    return [f"mix   hook volume {vol:.2f} (voice {over:+.0f} dB over the song)"]


def find_media(basename, dirs):
    for d in dirs:
        for root, _, files in os.walk(resolve(d)):
            if basename in files:
                return os.path.join(root, basename)
    return None


def find_project(name):
    """CapCut project folder by its name: local drafts first, then Ali's cloud-synced projects."""
    roots = [DRAFT_ROOT] + [os.path.join(DRAFT_ROOT, x) for x in os.listdir(DRAFT_ROOT) if x.startswith(".cloud_cache")]
    for r in roots:
        p = os.path.join(r, name)
        if os.path.exists(os.path.join(p, "Timelines", "project.json")):
            return p
    raise SystemExit(f"CapCut project '{name}' not found")


def find_timeline(project_dir, name_or_id):
    proj = load(os.path.join(project_dir, "Timelines", "project.json"))
    for t in proj["timelines"]:
        if name_or_id in (t["id"], t["name"]):
            return t["id"], t["name"]
    raise SystemExit(f"timeline '{name_or_id}' not in {[t['name'] for t in proj['timelines']]}")


PROFILES = os.path.join(ECOM, ".claude", "skills", "editing", "brands")


def load_profile(brand):
    for mother in os.listdir(PROFILES):
        p = os.path.join(PROFILES, mother, brand + ".json")
        if os.path.exists(p):
            return load(p)
    raise SystemExit(f"no brand profile '{brand}' in .claude/skills/editing/brands/")


def expand_spec(spec):
    """Short spec {brand, page, template: <id>, hook, song: <id>, texts} -> full spec, using the
    brand profile (.claude/skills/editing/brands/<mother>/<brand>.json)."""
    if not spec.get("brand"):
        return spec
    prof = load_profile(spec["brand"])
    page = spec.get("page", "us")
    pg = prof["pages"].get(page)
    if not pg or not pg.get("templates"):
        raise SystemExit(f"{spec['brand']} page '{page}' has no templates: {pg.get('status') if pg else 'unknown page'}"
                         f"{' / ' + prof['status'] if prof.get('status') else ''}")
    out = dict(spec)
    if isinstance(spec.get("template"), str) or not spec.get("template"):
        tid = spec.get("template") or pg["templates"][0]["id"]
        t = next((t for t in pg["templates"] if t["id"] == tid or t["timeline"] == tid), None)
        if not t:
            raise SystemExit(f"template '{tid}' not in {[t['id'] for t in pg['templates']]}")
        out["template"] = {"project": prof["capcut_project"], "timeline": t["timeline"]}
        if t.get("song_anchor"):
            out.setdefault("song_anchor", t["song_anchor"])
    out.setdefault("media_dirs", prof["media_dirs"] + [prof["product_folder"] + "/edit-assets"])
    out.setdefault("assets_dir", prof["product_folder"] + "/edit-assets")
    out.setdefault("extra_texts", pg.get("captions", {}).get("extra", []))
    if spec.get("caption_style"):
        st = next((x for x in pg.get("caption_styles", []) if x["id"] == spec["caption_style"]), None)
        if not st:
            raise SystemExit(f"caption style '{spec['caption_style']}' not in "
                             f"{[x['id'] for x in pg.get('caption_styles', [])]}")
        fill = {"<STORE>": spec.get("store"), "<TEAM>": spec.get("team")}
        for ph, val in fill.items():
            if ph in st["hook"] and not val:
                raise SystemExit(f"caption style '{st['id']}' needs \"{ph.strip('<>').lower()}\" in the spec")
        hook_txt = st["hook"]
        for ph, val in fill.items():
            hook_txt = hook_txt.replace(ph, val or "")
        texts = {"hook": hook_txt, "cta": st["cta"]}
        texts.update({k: v for k, v in (spec.get("texts") or {}).items() if v is not None})
        out["texts"] = texts
    if spec.get("song") and "/" not in spec["song"]:
        out["song"] = f"{prof['music_library']}/{spec['song']}"
    if not spec.get("timeline_name"):
        hook = os.path.splitext(os.path.basename(spec["hook"]))[0][:32] if spec.get("hook") else "template hook"
        song = out.get("song") or out["template"]["timeline"]
        out["timeline_name"] = f"{hook} | {song.split('/')[-1]}" + (f" | {spec['caption_style']}" if spec.get("caption_style") else "")
    if not spec.get("draft_name") and not spec.get("into_draft"):
        name = f"AUTO {prof['brand']} {page.upper()} {time.strftime('%Y-%m-%d')}"
        if os.path.exists(os.path.join(DRAFT_ROOT, name)):
            out["into_draft"] = name
        else:
            out["draft_name"] = name
    return out


def build_content(spec):
    tpl = spec["template"]
    pdir = find_project(tpl["project"]) if tpl.get("project") else resolve(tpl["project_dir"])
    tid, tname = find_timeline(pdir, tpl["timeline"])
    d = load(os.path.join(pdir, "Timelines", tid, "draft_content.json"))
    mats = d["materials"]
    replace = dict(spec.get("replace_media", {}))
    by_id = {}
    report = []
    # "hook" = the clip on screen at 0:00 (topmost video track); "rehook" = the next different clip
    # on that track. The slot takes the new clip's full length (or hook_in/hook_out) and the rest
    # of the timeline ripples: later clips/captions/audio move, the captions and song that span the
    # cut stretch (song grows at the front when it hands off to an end sound, else at the back).
    slots = slot_segments(d)
    for key in ("hook", "rehook"):
        if not spec.get(key):
            continue
        seg = slots.get(key)
        if not seg:
            raise SystemExit(f"template has no {key} slot")
        if key == "hook" and len(slots["hook_pieces"]) > 1:
            # old hook was cut into pieces (speed ramp / muted tail): treat it as one slot, like
            # Ali deleting the whole old hook before dropping the new clip in
            extra = slots["hook_pieces"][1:]
            last = extra[-1]["target_timerange"]
            seg["target_timerange"]["duration"] = last["start"] + last["duration"] - seg["target_timerange"]["start"]
            slots["track"]["segments"] = [x for x in slots["track"]["segments"] if all(x is not e for e in extra)]
            report.append(f"hook  old hook was {len(extra) + 1} pieces: replaced as one")
        new = resolve(spec[key])
        src_in = int(spec.get(f"{key}_in", 0) * US)
        full = probe(new)[0]
        src_out = int(spec[f"{key}_out"] * US) if spec.get(f"{key}_out") is not None else full
        if not 0 <= src_in < src_out <= full:
            raise SystemExit(f"{key}_in/{key}_out outside the clip (0 to {full / US:.2f}s)")
        delta = ripple_slot(d, seg, src_in, src_out - src_in, float(spec.get(f"{key}_speed", 1.0)),
                            spec.get("song_anchor", "start"))
        # give the slot its own material, so other uses of the same file (body pieces) stay put
        newm = copy.deepcopy(next(m for m in mats["videos"] if m["id"] == seg["material_id"]))
        newm["id"] = str(uuid.uuid4()).upper()
        mats["videos"].append(newm)
        seg["material_id"] = newm["id"]
        by_id[newm["id"]] = {"path": spec[key]}
        report.append(f"{key:5} slot {seg['target_timerange']['duration'] / US:.2f}s "
                      f"({'+' if delta >= 0 else ''}{delta / US:.2f}s ripple), video now {d['duration'] / US:.2f}s")
    if spec.get("song"):
        from song_library import get_song
        song = get_song(spec["song"])
        bed, end = classify_audio(d)
        if not bed:
            raise SystemExit("template timeline has no song to swap")
        if end and song.get("handoff") is not None:
            # Anchor the song on its handoff point, so it flows into the raw end sound. A longer slot
            # starts the song earlier; it never pushes the handoff later (Ali, 2026-10-07).
            replace[os.path.basename(bed["path"])] = {"path": song["file"], "source_end": song["handoff"]}
        elif song.get("anchor") == "end" and song.get("end") is not None:
            replace[os.path.basename(bed["path"])] = {"path": song["file"], "source_end": song["end"]}
        else:  # no end sound: the song's start is synced to the hook, extra length goes at the end (Ali)
            replace[os.path.basename(bed["path"])] = {"path": song["file"], "source_start": song["start"]}
        if end:
            if not song.get("end_sound"):
                raise SystemExit(f"template has an end sound but {spec['song']} has none in the library")
            replace[os.path.basename(end["path"])] = {"path": song["end_sound"]["file"],
                                                     "source_start": song["end_sound"]["start"]}
    dirs = spec.get("media_dirs", [])
    starts = {}

    for kind in ("videos", "audios"):
        for m in mats[kind]:
            old = os.path.basename(m["path"])
            if old.startswith("##_draftpath") or not old:
                continue
            r = by_id.get(m["id"]) or replace.get(old)
            new = resolve(r["path"]) if r else (m["path"] if os.path.exists(m["path"]) else
                                                locate_media(old, dirs, pdir, spec.get("assets_dir")))
            if not new or not os.path.exists(new):
                raise SystemExit(f"cannot find media for '{old}' (add to media_dirs or replace_media)")
            dur, w, h = probe(new)
            m["path"] = fwd(new)
            m["duration"] = dur
            if "material_name" in m:
                m["material_name"] = os.path.basename(new)
            if kind == "audios":
                m["name"] = os.path.basename(new)
            elif w:
                m["width"], m["height"] = w, h
            if r and "source_start" in r:
                starts[m["id"]] = ("start", int(r["source_start"] * US))
            elif r and "source_end" in r:
                starts[m["id"]] = ("end", int(r["source_end"] * US))
            report.append(f"{kind[:-1]:5} {old}  ->  {os.path.relpath(new, ECOM) if new.startswith(ECOM) else new}")

    mat_dur = {m["id"]: m["duration"] for k in ("videos", "audios") for m in mats[k]}
    segs_of = collections.defaultdict(list)
    for t in d["tracks"]:
        for s in t["segments"]:
            if s.get("source_timerange"):
                segs_of[s["material_id"]].append(s)
    # Shift every piece of a swapped file so its first piece starts at the new start ("start"), or its
    # last piece ends at the new handoff ("end"), keeping the spacing between pieces.
    # Materials that point at the same file move together.
    by_path = collections.defaultdict(list)
    for mid in starts:
        by_path[next(m["path"] for m in mats["audios"] + mats["videos"] if m["id"] == mid)].append(mid)
    for path, mids in by_path.items():
        segs = [s for mid in mids for s in segs_of[mid]]
        mode, t = starts[mids[0]]
        if mode == "start":
            first = min(segs, key=lambda s: s["target_timerange"]["start"])
            delta = t - first["source_timerange"]["start"]
        else:
            last = max(segs, key=lambda s: s["target_timerange"]["start"])
            delta = t - (last["source_timerange"]["start"] + last["source_timerange"]["duration"])
        if min(s["source_timerange"]["start"] for s in segs) + delta < 0:
            raise SystemExit(f"{os.path.basename(path)}: slot is longer than the song before its handoff")
        for s in segs:
            s["source_timerange"]["start"] += delta
    for t in d["tracks"]:
        for s in t["segments"]:
            sr = s.get("source_timerange")
            over = sr["start"] + sr["duration"] - mat_dur[s["material_id"]] if sr and s["material_id"] in mat_dur else 0
            if 0 < over <= 150_000:  # CapCut and ffprobe disagree on clip length by a frame or two
                if sr["start"] >= over:
                    sr["start"] -= over
                else:
                    sr["duration"] -= over
                continue
            if over > 0:
                raise SystemExit(f"segment of {s['material_id']} runs past end of its new file "
                                 f"({(sr['start'] + sr['duration']) / US:.2f}s > {mat_dur[s['material_id']] / US:.2f}s)")

    if spec.get("song"):
        report += set_end_sound_volume(d, spec["song"].split("/", 1)[0])
    if spec.get("hook"):
        report += set_hook_volume(d, spec)

    texts = spec.get("texts") or []
    text_by_id = {m["id"]: m for m in mats["texts"]}
    tsegs = sorted((s for t in d["tracks"] if t["type"] == "text" for s in t["segments"]),
                   key=lambda s: s["target_timerange"]["start"])
    order = [s["material_id"] for s in tsegs]
    if isinstance(texts, dict):  # by role: hook = longest caption starting at 0:00, cta = last caption
        roles = {}
        at0 = [s for s in tsegs if s["target_timerange"]["start"] < FRAME]
        if at0:
            roles["hook"] = max(at0, key=lambda s: s["target_timerange"]["duration"])["material_id"]
        extras = set(spec.get("extra_texts", []))
        body = [s for s in tsegs if json.loads(text_by_id[s["material_id"]]["content"])["text"] not in extras]
        if body:
            roles["cta"] = body[-1]["material_id"]
        for role, new_text in texts.items():
            if new_text is None:
                continue
            if role not in roles:
                raise SystemExit(f"template has no '{role}' caption (roles: {list(roles)})")
            set_text(text_by_id[roles[role]], new_text)
            report.append(f"text  {role} -> {new_text!r}")
        texts = []
    for i, new_text in enumerate(texts):
        if new_text is not None and i < len(order):
            set_text(text_by_id[order[i]], new_text)
            report.append(f"text  #{i + 1} -> {new_text!r}")

    for name in spec.get("drop_clips", []):
        report += drop_clip(d, name)
    for role, st in (spec.get("text_style") or {}).items():
        report += style_text(d, role, st, spec.get("extra_texts", []))

    d["id"] = str(uuid.uuid4()).upper()
    d["fps"] = float(spec.get("fps", 60))  # Ali exports at 60 fps; CapCut's export dialog defaults to the project fps
    return d, tname, report


def write_draft(spec, d):
    if not SKELETON:
        raise SystemExit("No empty CapCut project to copy from: open CapCut, create one empty project, close CapCut, retry.")
    name = spec["draft_name"]
    dest = os.path.join(DRAFT_ROOT, name)
    if os.path.exists(dest):
        raise SystemExit(f"draft folder already exists: {dest}")
    root_meta_p = os.path.join(DRAFT_ROOT, "root_meta_info.json")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    shutil.copy2(root_meta_p, os.path.join(BACKUP_DIR, f"root_meta_info.{time.strftime('%Y%m%d-%H%M%S')}.json"))

    tid = d["id"]
    now_us = int(time.time() * US)
    shutil.copytree(SKELETON, dest, ignore=shutil.ignore_patterns("Timelines", "*.bak", "*.tmp", "key_value.json"))
    tdir = os.path.join(dest, "Timelines", tid)
    os.makedirs(os.path.join(tdir, "common_attachment"))
    sk_t = os.path.join(SKELETON, "Timelines", load(os.path.join(SKELETON, "Timelines", "project.json"))["main_timeline_id"])
    for f in ("attachment_editing.json", "attachment_pc_common.json", "draft.extra"):
        shutil.copy2(os.path.join(sk_t, f), tdir)
    for f in os.listdir(os.path.join(sk_t, "common_attachment")):
        shutil.copy2(os.path.join(sk_t, "common_attachment", f), os.path.join(tdir, "common_attachment"))
    for p in (os.path.join(tdir, "draft_content.json"), os.path.join(dest, "draft_content.json")):
        dump(d, p)

    dump({"config": {"color_space": -1, "hdr_vivid": False, "mixed_track_mode_on": False,
                     "render_index_track_mode_on": False, "use_float_render": False},
          "create_time": now_us, "id": str(uuid.uuid4()).upper(), "main_timeline_id": tid,
          "timelines": [{"create_time": now_us, "id": tid, "is_marked_delete": False,
                         "name": spec.get("timeline_name") or "Timeline 01", "update_time": now_us}],
          "update_time": now_us, "version": 0}, os.path.join(dest, "Timelines", "project.json"))
    dump({"dockItems": [{"dockIndex": 0, "ratio": 1, "timelineIds": [tid],
                         "timelineNames": [spec.get("timeline_name") or "Timeline 01"]}],
          "layoutOrientation": 1}, os.path.join(dest, "timeline_layout.json"))

    meta = load(os.path.join(SKELETON, "draft_meta_info.json"))
    draft_id = str(uuid.uuid4()).upper()
    meta.update(draft_fold_path=fwd(dest), draft_id=draft_id, draft_name=name,
                tm_draft_create=now_us, tm_draft_modified=now_us, tm_duration=d["duration"])
    dump(meta, os.path.join(dest, "draft_meta_info.json"))
    with open(os.path.join(dest, "draft_settings"), "w") as f:
        f.write(f"[General]\ndraft_create_time={now_us // US}\ndraft_last_edit_time={now_us // US}\n"
                "real_edit_seconds=0\nreal_edit_keys=0\n")

    hook = next((m["path"] for m in d["materials"]["videos"]), None)
    if hook:
        try:  # cover thumbnail only; ffmpeg.exe can be blocked by Windows Application Control
            import av
            with av.open(hook) as f:
                frame = next(f.decode(video=0))
                frame.to_image().resize((360, 640)).save(os.path.join(dest, "draft_cover.jpg"))
        except Exception:
            pass

    rm = load(root_meta_p)
    sk_name = os.path.basename(SKELETON)
    entry = copy.deepcopy(next(e for e in rm["all_draft_store"]
                               if os.path.basename(e["draft_fold_path"].replace("\\", "/").rstrip("/")) == sk_name))
    entry.update(draft_cover=fwd(dest) + "\\draft_cover.jpg", draft_fold_path=fwd(dest), draft_id=draft_id,
                 draft_json_file=fwd(dest) + "\\draft_content.json", draft_name=name,
                 tm_draft_create=now_us, tm_draft_modified=now_us, tm_duration=d["duration"])
    rm["all_draft_store"].insert(0, entry)
    rm["draft_ids"] = rm.get("draft_ids", 0) + 1
    dump(rm, root_meta_p)
    return dest


def bump_project(dest, duration):
    """Make this project the newest one, so it is the first card on CapCut's home screen."""
    now_us = int(time.time() * US)
    rp = os.path.join(DRAFT_ROOT, "root_meta_info.json")
    rm = load(rp)
    for e in rm["all_draft_store"]:
        if os.path.normcase(os.path.normpath(e["draft_fold_path"])) == os.path.normcase(os.path.normpath(dest)):
            e["tm_draft_modified"] = now_us
            e["tm_duration"] = duration
    rm["all_draft_store"].sort(key=lambda e: -e.get("tm_draft_modified", 0))
    dump(rm, rp)
    mp = os.path.join(dest, "draft_meta_info.json")
    m = load(mp); m["tm_draft_modified"] = now_us; m["tm_duration"] = duration; dump(m, mp)


def add_timeline(spec, d):
    """Add the built timeline as a new tab inside an existing local draft (spec: into_draft, timeline_name)."""
    dest = os.path.join(DRAFT_ROOT, spec["into_draft"])
    proj_p = os.path.join(dest, "Timelines", "project.json")
    if not os.path.exists(proj_p):
        raise SystemExit(f"no CapCut draft at {dest}")
    proj = load(proj_p)
    name = spec.get("timeline_name") or f"Timeline {len(proj['timelines']) + 1:02d}"
    existing = next((t for t in proj["timelines"] if t["name"] == name and not t.get("is_marked_delete")), None)
    if existing and not spec.get("overwrite"):
        raise SystemExit(f"timeline '{name}' already exists in {spec['into_draft']} (add \"overwrite\": true to rebuild it)")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for f in ("project.json",):
        shutil.copy2(proj_p, os.path.join(BACKUP_DIR, f"{spec['into_draft']}.{f}.{stamp}"))

    tid, now_us = d["id"], int(time.time() * US)
    if existing:  # rebuild in place: same timeline id and folder, new content
        tid = d["id"] = existing["id"]
        tdir = os.path.join(dest, "Timelines", tid)
        shutil.copy2(os.path.join(tdir, "draft_content.json"),
                     os.path.join(BACKUP_DIR, f"{spec['into_draft']}.{tid}.draft_content.{stamp}.json"))
        for f in ("draft_content.json.bak", "template-2.tmp", "template.tmp"):
            if os.path.exists(os.path.join(tdir, f)):
                os.remove(os.path.join(tdir, f))
        shutil.rmtree(os.path.join(tdir, "attachment", "patch"), ignore_errors=True)
        dump(d, os.path.join(tdir, "draft_content.json"))
        if load(proj_p).get("main_timeline_id") == tid:
            dump(d, os.path.join(dest, "draft_content.json"))
        existing["update_time"] = now_us
        proj["main_timeline_id"] = tid
        dump(proj, proj_p)
        dump(d, os.path.join(dest, "draft_content.json"))
        bump_project(dest, d["duration"])
        return f"{dest}  [timeline '{name}' rebuilt]"
    tdir = os.path.join(dest, "Timelines", tid)
    os.makedirs(os.path.join(tdir, "common_attachment"))
    sk_t = os.path.join(SKELETON, "Timelines", load(os.path.join(SKELETON, "Timelines", "project.json"))["main_timeline_id"])
    for f in ("attachment_editing.json", "attachment_pc_common.json", "draft.extra"):
        shutil.copy2(os.path.join(sk_t, f), tdir)
    for f in os.listdir(os.path.join(sk_t, "common_attachment")):
        shutil.copy2(os.path.join(sk_t, "common_attachment", f), os.path.join(tdir, "common_attachment"))
    dump(d, os.path.join(tdir, "draft_content.json"))

    proj["timelines"].append({"create_time": now_us, "id": tid, "is_marked_delete": False,
                              "name": name, "update_time": now_us})
    proj["update_time"] = now_us
    proj["main_timeline_id"] = tid  # CapCut opens + exports the main timeline
    dump(proj, proj_p)
    dump(d, os.path.join(dest, "draft_content.json"))
    bump_project(dest, d["duration"])
    return f"{dest}  [timeline '{name}']"


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "timelines":
        proj = load(os.path.join(sys.argv[2], "Timelines", "project.json"))
        for t in proj["timelines"]:
            print(t["id"], t["name"])
        return
    if len(sys.argv) < 3 or sys.argv[1] != "build":
        raise SystemExit(__doc__)
    spec = expand_spec(load(sys.argv[2]))
    d, tname, report = build_content(spec)
    print(f"project: {spec.get('into_draft') or spec.get('draft_name')}"
          f"{'  (new timeline ' + repr(spec.get('timeline_name')) + ')' if spec.get('into_draft') else ''}")
    print(f"template timeline: {tname}   duration {d['duration'] / US:.2f}s")
    print("\n".join("  " + r for r in report))
    if "--dry-run" in sys.argv:
        return
    if capcut_running():
        raise SystemExit("CapCut is open. Close it fully (also from the tray) and run again.")
    print("written:", add_timeline(spec, d) if spec.get("into_draft") else write_draft(spec, d))


if __name__ == "__main__":
    main()
