# Set up your brands (for Claude Code)

The editing skill never edits from scratch. It copies one of the user's own finished CapCut timelines and swaps only the hook (plus captions, and sometimes the song). So every brand needs a **profile** that says which timelines are templates, which songs and captions exist, and how the song behaves. Build them from the user's CapCut projects, one brand at a time, and confirm each with the user.

## 1. Organize CapCut (the user, once)
- One CapCut project per brand (and per page if a brand has a second-language page).
- Inside it, one finished timeline per song, named after the song (e.g. "Tennessee Whiskey", "Halo"). Two cuts of the same song = two timelines ("V1 Halo", "V2 Halo").
- Same body clips in every timeline; only hook, song and captions differ.

## 2. Read the projects
`python tools/capcut_scan.py` (all) or `python tools/capcut_scan.py "<project>"` (one, with every clip). For each timeline it shows the hook at 0:00, the song section, the raw end sound (music box), the captions, and `template OK` or why not.
Show the user a table per brand: timeline | song + section | hook length | captions. Ask which timelines are templates and which songs perform best (they go first).

## 3. Songs
Edit `music/projects.json` (CapCut project name prefix -> brand slug), then `python tools/song_library.py scan`. It copies the songs into `music/<brand>/` and writes `music/library.json` with each song's section and handoff point. Needed only for brands where songs are swapped (structure brands); song-timeline brands keep each timeline's own song.

## 4. Write the profile
Copy `.claude/skills/editing/brands/_TEMPLATE.json` to `brands/music-box/<brand>.json` or `brands/door-beam/<brand>.json` (folder = product line; rename freely, the tools search every folder). Fill:
- `brand`, `display`, `product_folder`, `media_dirs` (folders where the template's body clips live, so the tool can find them), `capcut_project`, `export_dir` (`exports/<line>/<brand>/<page>`).
- `pages.us.templates`: one entry per template timeline: `{"id", "timeline", "rank", "best", "song", "hook_len"}`. Car door projector brands add `"song_anchor": "start"` (see below).
- `pages.us.caption_styles`: the user's caption pairs, verbatim from the timelines: `{"id", "best", "hook", "cta"}`. Use `<STORE>` / `<TEAM>` placeholders where the store or team changes per video. Pair store-claim hooks ("RUN to TARGET", "<BRAND> x WALMART") with the reveal CTA ("JK.. we sell them 🤭 ..."), others with the plain CTA ("Comment "WANT" to GET one🔥").
- `pages.us.captions.extra`: lines that must never be treated as the CTA (e.g. "link in bio 🔗").
- `songs` (structure brands): `["<library>/<song id>", ...]` from `song_library.py list <library>`.
- `workflow`, `mix`, `notes`: plain-English rules the user tells you.
Use `brands/examples/` as format references (the original owner's brands; their projects are not on this PC).

## 5. The song rules (already in the tools)
- **Music box** (raw end sound under the fridge): the song is placed by its **handoff** into the raw clip. A longer hook starts the song earlier; the handoff never moves. Keep each song timeline's own mix.
- **Car door projector** (one song, no raw clip): the song's **start** is synced to the hook, so a longer hook extends the song at the **end** (`"song_anchor": "start"`). If the user's edits show a song whose END is always the same point, ask them which rule that song follows.
- New hooks play at normal speed; the hook voice is set ~3 dB over the song; hooks the user muted stay muted.

## 6. Test each brand
For every template: one dry run with a short and a long hook (`capcut_draft.py build ... --dry-run`), check no gaps / captions / song section. Then one real `capcut_export.py ... --open` and let the user watch it. When they fix something by hand in CapCut, diff their timeline against the rebuild and fold the change into the profile (song / mix: `song_library.py learn "<project>" "<timeline>"`).
