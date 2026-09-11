# Video Player

Standalone Raw Frame video browser and player.

Place one or more video files in:

```text
assets/videos/
```

Supported suffixes:

- `.mp4`
- `.mov`
- `.mkv`
- `.webm`
- `.avi`

The app requires the system `ffmpeg` command. Audio is attempted with `ffplay`
when available and can be disabled with:

```bash
LAFVIN_VIDEO_AUDIO=0
```

Run during development:

```bash
lafvin-hat app run apps/video_player
```

For a persistent install:

```bash
lafvin-hat app install apps/video_player
lafvin-hat app start dev.lafvin.video-player
```

Videos are sorted by filename. The selection screen shows the current file and
its position in the list.

Controls:

- single click: select the next video
- double click: play the selected video
- triple click: stop playback and return Home

During playback, single-click stops the current video and returns to the
selection screen. Double-click is ignored so it cannot queue an unexpected
action. The selected video loops when it reaches the end. Triple-click remains
available through the Runtime shell and returns Home directly.

The video player draws video and message frames directly instead of using the
UI toolkit. Triple-click exits through the Runtime shell, like the other
foreground apps.
