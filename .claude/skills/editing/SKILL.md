---
name: editing
description: Edit a finished hook into a full reel with CapCut, for every music box brand and every car door projector brand that has a profile in .claude/skills/editing/brands/. Use when the user says "edit it", "edit this video", "now edit the video", "make the reel", "put it together", "make a CapCut project", "change the hook/song/caption", "I want to tweak it", or right after they approve a hook in a replication or product chat. Asks song + caption, builds the CapCut timeline, exports it with CapCut invisibly, and opens the video for them.
---

# Editing: approved hook -> CapCut reel -> exported video

The user's flow (2026-10-08):
1. A hook is generated and the user says "yes, the hook is good".
2. **You ask: which song + which caption** (one AskUserQuestion call).
3. You build the reel as a CapCut timeline (clone of the user's own timeline, hook swapped), **CapCut exports it invisibly**, and the video opens in the user's player.
4. If the user wants changes ("I don't like it, I need to tweak a few things"), you open that exact CapCut project on their screen; they tweak and export it themselves.

**Never touch the user's cursor, keyboard or focus.** They keep working while you edit and export (CapCut runs on a hidden Windows desktop).

## Files

| What | Where |
|---|---|
| Brand profile: templates, caption styles, songs, rules | `.claude/skills/editing/brands/<music-box or door-beam>/<brand>.json` (read it first) |
| Build + CapCut export in one go | `python tools/capcut_export.py <spec.json> --open` |
| Build only (dry run, no CapCut) | `python tools/capcut_draft.py build <spec.json> --dry-run` |
| Open a project for the user to tweak | `python tools/capcut_open.py "<project>" "<timeline>"` |
| Learn the user's song / mix fix | `python tools/song_library.py learn "<project>" "<timeline>"` |
| Songs + sections | `music/library.json` (readable: `music/README.md`) |
| Exported videos + log | `exports/<mother>/<brand>/<page>/`, `exports/LOG.csv` (see `exports/README.md`) |
| Saved specs | `products/<brand folder>/edits/<YYYY-MM-DD>/<name>.json` |

## Step 0: read the room (no questions)
- **Brand + page** from this chat (product folder / replication run). Load the profile. Use the page the profile defines (`us` unless a brand has several pages, e.g. a French page).
- **Hook clip** = the clip the user just approved. If unclear, ask only which clip.
- **Store / team** the hook shows (for `<STORE>` / `<TEAM>` captions): look at the clip (frame sheet), or the file name (dodgers, yankees, target, walmart...).
- **Original's caption** (replications only): the competitor's on-screen text, read from `<run>/source/sheet-*.jpg` + `full-*.png`.

## Step 1: ask (ONE AskUserQuestion call, two questions)
- **Song**: options from the profile (best ones first, max 4 + "Other"; list all of them in the question text).
  - Song-timeline brands (each CapCut timeline holds one song, named after it): song = template timeline (`"template": "<id>"`, no `"song"`).
  - Structure brands (templates are layouts, e.g. full-clip vs hook + clip): template is picked by the clip, song is separate (`"song": "<song id>"`).
- **Caption**: the profile's `caption_styles` (the `best` one first), each option showing the exact text with store / team filled in; plus the original's caption if this is a replication. The user can type their own under "Other" (goes in `"texts": {"hook": "...", "cta": "..."}`).

## Step 2: build + export
Write the spec to `products/<brand folder>/edits/<date>/<hook> <song> <caption>.json`, then:
```
python tools/capcut_export.py "<spec.json>" --open
```
Spec examples:
```json
{"brand": "noah-kahan", "page": "us", "template": "stick-season-1",
 "hook": "products/noah-kahan/final-clips/1-hook/Face Reaction/R3-uo-lookalike-FINAL.mp4",
 "caption_style": "do-not-show"}
```
```json
{"brand": "walk-off-lights", "page": "us", "template": "full-video",
 "hook": "products/car-door-projector/baseball/final-clips/full-videos/dodgers-shelf-to-door-FINAL.mp4",
 "song": "free-bird", "caption_style": "do-not-show-team", "team": "Dodgers"}
```
What the tool does: builds the timeline into the day's project `AUTO <brand> <PAGE> <date>` (one new timeline per video, named `<hook> | <song> | <caption>`), makes it the project's main timeline, starts CapCut on a hidden desktop, exports 1080x1920 at 60 fps, moves the mp4 to `exports/...`, logs it in `exports/LOG.csv`, closes CapCut, opens the video. About 25 s.
- If it says "CapCut is open on your screen": ask the user to save + close CapCut (tray too). Never kill CapCut while it's on their screen.
- Optional spec keys: `hook_in` / `hook_out` (trim the hook, seconds), `hook_volume` (override), `store`, `team`, `texts`.

Then tell the user in a few lines: file path, length, song + section, captions, and the CapCut project + timeline name.

## Step 3: tweaks
"I want to tweak it" -> `python tools/capcut_open.py "AUTO <brand> <PAGE> <date>" "<timeline name>"` (CapCut must be closed). The user edits and exports themselves, or saves + closes and says "export it" -> `python tools/capcut_export.py "<spec.json>" --no-build --open` (exports the project's main timeline).
If they say what they changed (or "check my changes"): diff their timeline against a rebuild of the spec and show the differences in a table. Song / mix changes -> `song_library.py learn`. Anything else -> update the brand profile and save a feedback memory with the why.

## Upscaling
Only when the user asks ("upscale it"): use the `upscaling` skill (Higgsfield Topaz 2k / Proteus / 60 fps on the hidden desktop, price confirmed with the user first, never above 15 credits). Pass the exact exported file.

## What the tool handles automatically (don't redo by hand)
- **Hook length**: new hook at normal speed; everything after it ripples. Hook caption stretches/shrinks, CTA moves with the end clip.
- **Song (music box)**: placed by its handoff into the raw "box plays the song" clip. A longer hook starts the song EARLIER; the handoff never moves. Song timelines keep the user's own mix.
- **Song (Door Beam, no raw end sound)**: the song's start is synced to the hook, so a longer hook extends the song at the END.
- **Hook voice** about 3 dB over the song (capped at 6x). Hooks the user muted stay muted; silent hook clips are left alone.
- **Old hook in pieces** (speed ramp / muted tail) is replaced as one clip. "link in bio" lines stay put.

## Brand notes
Every brand's specifics (CapCut project, song timelines, caption styles, song rule) live in its profile `.claude/skills/editing/brands/<mother>/<brand>.json`. Build them with SETUP-YOUR-BRANDS.md. `brands/examples/` holds the original owner's profiles as format references only (their CapCut projects, songs and captions are not on this PC).

## Hard rules
1. Never move the user's cursor, type, or take focus. Exports run on the hidden desktop only.
2. Never write into the user's own CapCut projects (`.cloud_cache_*`): they are read-only templates. Output goes to `AUTO ...` local projects.
3. CapCut stays on 9.5.0.4050 (never accept its "Version update" window). The click map in `tools/capcut_export.py` is for this version.
4. Always ask song + caption. Captions verbatim from the profile; no em dashes.
5. ffmpeg.exe is blocked on this PC: tools use ffprobe + PyAV. Don't add ffmpeg calls.
6. Final videos are always CapCut exports (never `tools/capcut_render.py`, which is only a rough preview).
