# Editing + Upscaling skills (Claude Code)

Two Claude Code skills that turn an approved hook into a finished, CapCut-exported reel, and upscale it on Higgsfield, without touching your mouse, keyboard or screen.

**The flow**
1. Your Claude generates a hook; you say "yes, the hook is good, edit it".
2. Claude asks two things: **which song** and **which caption**.
3. Claude builds the reel as a timeline inside **your own CapCut** (a copy of one of your finished timelines with the hook swapped), **CapCut exports it on a hidden Windows desktop**, and the video opens in your player. About 25 seconds.
4. Want changes? "I want to tweak it": Claude opens that exact CapCut project on your screen, you tweak and export.
5. "Upscale it": Claude uploads the export to higgsfield.ai/upscale (Topaz Video, 2k, Proteus, Auto, 60 fps), tells you the credit price, and only fires after your yes. Never above 15 credits.

Built for two product lines:
- **Music box**: hook -> body (opening box) -> fridge shot, with a song that hands off into a short "raw" clip of the box playing the song.
- **Car door projector**: hook -> body -> projection, one song under the whole video.

**Start here**
1. `INSTALL-FOR-CLAUDE.md`: prerequisites + install (give this file to your Claude Code).
2. `SETUP-YOUR-BRANDS.md`: your Claude reads your CapCut projects and builds one profile per brand (songs, captions, templates).
3. Then just say "edit it" after a hook is approved.

**What's inside**
```
.claude/skills/editing/      SKILL.md + brands/ (your profiles go here; examples/ = format references)
.claude/skills/upscaling/    SKILL.md
tools/                       capcut_draft.py (build), capcut_export.py (build + CapCut export), capcut_open.py (open to tweak),
                             capcut_scan.py (read your CapCut projects), song_library.py (songs), higgs_upscale.py (upscale),
                             _hiddendesk.py + _wincap.py (hidden desktop + background clicks)
music/                       projects.json (CapCut project -> brand), mix.json, library.json (built by song_library.py scan)
exports/                     finished videos per brand + LOG.csv
```
