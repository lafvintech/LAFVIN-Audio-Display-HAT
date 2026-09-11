# System Status

Bundled Runtime and device status application. It is a compact Raw Frame UI
toolkit page and one of the proving grounds for the app-facing toolkit.

The app displays two pages from `runtime.status`.

Page 1, System Monitor:

- CPU usage
- Memory usage
- Temperature, labeled `TEMP °C` so the unit reads next to the label instead
  of after each value
- Storage usage

Page 2, Device Info:

- Runtime uptime
- Raspberry Pi model
- IP address
- installed app count
- hostname

Single-click switches pages. Triple-click returns Home through the normal
foreground-app lifecycle.

Run during development:

```bash
lafvin-hat app run apps/system_status
```

For a persistent install, use `app-install` and `app-start` explicitly.

