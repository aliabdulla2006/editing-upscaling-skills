# Install (for Claude Code)

Claude: follow these steps in order, check each one, and tell the user what you found. Ask before installing anything.

## 1. Prerequisites

| # | What | Why | Check |
|---|---|---|---|
| 1 | **Windows 10 or 11** PC, display scaling **100%** recommended | the hidden desktop + background clicks are Win32; the CapCut click map was measured at 100% | Settings > Display > Scale |
| 2 | **Claude Code** running on that PC (CLI, VS Code or desktop app; not claude.ai in the browser) | the skills run local tools | `claude --version` |
| 3 | **CapCut desktop, international version 9.5.0.4050**, logged in | the drafts and the export click map are for this version. CapCut 10.x reportedly rejects script-built drafts | `dir "%LOCALAPPDATA%\CapCut\Apps"` shows `9.5.0.4050` |
| 4 | **CapCut must NOT auto-update.** Never click its "Version update" window | an update can break the draft format and the click map | (tell the user) |
| 5 | **One empty local CapCut project** (CapCut > Create project > close it right away) | new projects are copied from a project CapCut made itself | `dir "%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft"` |
| 6 | **Your finished reels as CapCut timelines**, one project per brand, ideally one timeline per song named after the song | these are the templates (see SETUP-YOUR-BRANDS.md) | `python tools/capcut_scan.py` |
| 7 | **Python 3.12+** | the tools | `python --version` |
| 8 | Python packages: `pip install -r requirements.txt` (av, numpy, pillow, playwright) | video/audio reading, loudness, browser control | `python -c "import av, numpy, PIL, playwright"` |
| 9 | **ffprobe** on PATH (comes with FFmpeg: `winget install Gyan.FFmpeg`) | reads clip lengths | `ffprobe -version` |
| 10 | **Google Chrome** at `C:\Program Files\Google\Chrome\Application\chrome.exe` | the upscaler drives a real Chrome (Higgsfield blocks test browsers) | file exists |
| 11 | **Higgsfield account** with credits (the user's own) | Topaz upscale | logs in once in step 4 |
| 12 | **Higgsfield connector for Claude** (claude.ai > Settings > Connectors > Higgsfield, same account) | the upscale skill uses its `show_generations` / `jobs_wait` tools to find and download the finished upscale | Claude can call `mcp__claude_ai_Higgs__balance` and the workspace is the user's own |

FFmpeg itself (`ffmpeg.exe`) is not needed; the tools use PyAV. If Windows ever blocks `ffmpeg.exe`, nothing breaks.

## 2. Copy into the project
Put the contents of this repo in the root of the user's Claude Code project (the folder Claude Code opens), keeping the paths:
`.claude/skills/editing`, `.claude/skills/upscaling`, `tools/`, `music/`, `exports/`, `requirements.txt`.
Merge `.gitignore` lines into the project's `.gitignore` (media files, `.browser/`, `tools/_capcut_backups/` must never be committed: `.browser/` holds the Higgsfield login).
Restart Claude Code so it loads the two skills.

## 3. Test CapCut (free)
1. CapCut fully closed (tray icon too).
2. `python tools/capcut_scan.py` lists the user's projects and timelines. At least one should say `template OK`.
3. Build one brand profile (SETUP-YOUR-BRANDS.md), then a dry run: `python tools/capcut_draft.py build <spec.json> --dry-run`.
4. One real build + export: `python tools/capcut_export.py <spec.json> --open`. Nothing should appear on screen; after ~25 s the video opens and lands in `exports/`.
   - If CapCut's version is not 9.5.0.4050 the tool warns: the click points (`HOME_FIRST_CARD`, `EDITOR_EXPORT_BTN`, ... at the top of `tools/capcut_export.py`) may need re-measuring. Do it with screenshots of the hidden windows (`tools/_wincap.py capture()`), never by moving the user's mouse.
   - A "Couldn't output sound" popup (PC volume muted) is handled automatically.

## 4. Higgsfield login (one time)
Open the dedicated Chrome profile visibly:
```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="<project>\.browser\higgsfield" --remote-debugging-port=9333 https://higgsfield.ai/
```
The user logs in with their own Higgsfield account. Then `python tools/higgs_upscale.py close`. From now on it runs on the hidden desktop.
Test (free, never fires): `python tools/higgs_upscale.py prepare "<an exported mp4>"` -> settings verified + a price (normally 6 to 10 credits).

## 5. Rules the skills enforce (keep them)
- Never move the user's cursor, type, or take focus. Exports and upscales run on the hidden desktop.
- Never write into the user's own (cloud-synced) CapCut projects; builds go into `AUTO <brand> <PAGE> <date>` local projects.
- Always ask song + caption before building; always confirm the exact credit price before an upscale; never fire an upscale above 15 credits (fix: Original, wait 3 s, 2k).
- Final videos are CapCut exports only.
