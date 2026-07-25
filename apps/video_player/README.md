# Video Player

Standalone V2-M5 Raw Frame video playback app.

Place the playback file at:

```text
assets/videos/test.mp4
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

To play a different file, edit `VIDEO_FILENAME` in `main.py`.

The video player draws video and message frames directly instead of using the
UI toolkit. Triple-click exits through the Runtime shell, like the other
foreground apps.
