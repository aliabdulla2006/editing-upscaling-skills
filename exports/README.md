# Exports

Every finished reel, exported by CapCut itself, lands here. One place, one naming rule, one log. the user's old `Desktop\FULLY DONE\` folders are left as they are.

```
exports/
  music-box/
    celine-dion/us/   celine-dion/fr/
    noah-kahan/us/
    golden-age/us/
  door-beam/
    walk-off-lights/us/
    merry-drive/us/
    zodiac-drive/us/
  _incoming/          <- CapCut writes here first; the exporter moves the file to its brand folder
  LOG.csv             <- one row per export (tracked in git)
```

**File name:** `YYYY-MM-DD_HHMM <hook clip> - <song> - <caption style>.mp4`, e.g.
`2026-10-08_2140 reaction-R2i-target-phone-doubletake - Stick Season 1 - do-not-show.mp4`

**LOG.csv columns:** `exported_at, brand, page, file, capcut_project, timeline, hook, song, caption_style, spec, posted`
(`posted` is empty until the video is scheduled; fill it with the date / platform.)

**How a file gets here:** `python tools/capcut_export.py <spec.json>` (called by the `editing` skill). It opens the CapCut project on a hidden Windows desktop, exports 1080x1920 at 60 fps with CapCut, moves the mp4 here, logs it, closes CapCut. the user's cursor, keyboard and screen are never touched. "Sync exported videos to space" stays on.

The mp4 files are gitignored (`*.mp4`); this README and LOG.csv are tracked.
