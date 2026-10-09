---
name: upscaling
description: Upscale a finished video on Higgsfield with the user's exact Topaz settings (2k, Proteus, Auto, 60 fps interpolation), invisibly on a hidden desktop. Use when the user says "upscale it", "upscale this video", "upscale the final video", "make it 2K", "run Topaz", or asks for the upscaled version of an exported reel. Always tells the user the credit price and waits for their yes before firing; never fires above 15 credits.
---

# Upscaling (Higgsfield web, Topaz Video)

The user's settings (2026-10-09), set on **higgsfield.ai/upscale**:

| Setting | Value |
|---|---|
| Model | **Topaz Video** |
| Scale factor | **2k** |
| Enhancement | ON, preset **Proteus** (the page defaults to "Starlight Precise 2.5", which is expensive: always switch) |
| Parameters | **Auto** |
| Frame Interpolation | ON, **60 fps** |
| Slow motion | **1x** |

A normal price is **6 to 10 credits** per reel.

Why the website: the Higgsfield MCP `upscale_video` tool can't do this (its Topaz only offers 1080p / 2160p, no preset, no fps). Don't use it for the user's upscales.

## The rules
1. **Never fire above 15 credits.** A big number (like 82 or 103) means the page is wrong, not that the clip is expensive.
2. **Inflated price fix (the user's):** click **Original**, wait 3 seconds, click **2k** again. The price drops back to normal (82 -> 8 on 2026-10-09). The tool does this automatically, up to 3 times. Still above 15 after that: stop and tell the user.
3. **Always confirm the price with the user before firing**, for every single upscale: "This upscale costs **X credits**, fire?" (a yes for this exact job; no batch approvals). Show them the settings screenshot if anything looked off.
4. **Never touch the user's screen, cursor or keyboard.** Chrome runs on the hidden desktop.
5. Always pass the **exact file** to upscale (other agents export into the same folders; never "the newest file").

## Steps
1. **Prepare** (free, never fires):
   ```
   python tools/higgs_upscale.py prepare "<path to the exported mp4>"
   ```
   Uploads the file, sets every setting above, applies the price fix if needed, saves a screenshot of the settings panel to `exports/_incoming/upscale-settings.png`, and prints the price. Look at the screenshot yourself before asking the user.
2. **Ask the user:** "Upscale of `<file name>` costs **X credits** (Topaz Video, 2k, Proteus, Auto, 60 fps). Fire?" If X > 15 or the screenshot shows other settings: don't ask to fire; say what's wrong.
3. **Fire** (only after their yes, same file):
   ```
   python tools/higgs_upscale.py fire "<same path>"
   ```
   It re-checks the price (refuses if > 15 or if it changed since prepare: then ask the user again), clicks Upscale, waits for the result (up to 30 min) and downloads it next to the original as `<name> - 2k60.mp4`.
4. **Verify** with ffprobe: 60 fps, about 1440x2560 for a 1080x1920 source (2k), same duration. Then open it for the user (`os.startfile`).
5. When done for the session: `python tools/higgs_upscale.py close`.

**Known issue (first real runs, 2026-10-09):** the upscale itself works, but `fire` never sees the finished video on the page and gives up after 30 min ("no finished video showed up"). Get the result like this instead (free):
1. Higgs MCP `show_generations` (type video, only_completed false): the upscales are model `topaz_video`, output 1152x2048, 60 fps.
2. Other sessions upscale on the same account, so match by duration: `ffprobe` the `rawUrl` (or the `input_video.url` of a job still rendering) and compare with the exported file's length.
3. `curl` the `rawUrl` to `<name> - 2k60.mp4` next to the original and verify 1152x2048, 60 fps, same duration. A job still `in_progress` can be waited on with `jobs_wait`.

Several reels at once: `prepare` puts each file in its own tab (tagged window.name), so prepare them all, show the user every price, then fire each (one background `fire` per file, a few seconds apart). Never re-fire to "retry" without the user's yes: that spends credits twice.

## First-time login (only if the tool says the profile is missing or Higgsfield shows logged out)
The automation uses its own Chrome profile at `.browser/higgsfield/` (gitignored). To log in again, open it visibly once:
```
"C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="<ecom>\.browser\higgsfield" --remote-debugging-port=9333 https://higgsfield.ai/
```
Ask the user to log in with their own Higgsfield account (not their brother's), then close it with `python tools/higgs_upscale.py close`. After that everything runs hidden again.
