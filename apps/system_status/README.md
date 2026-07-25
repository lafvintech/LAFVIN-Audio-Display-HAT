# System Status

Bundled Runtime and device status application. It is a compact Raw Frame UI
toolkit page and one of the proving grounds for the app-facing toolkit.

The app displays a snapshot from `runtime.status`:

- Runtime uptime
- Raspberry Pi model
- IP address
- installed app count
- temperature
- storage usage

Run during development:

```bash
lafvin-hat app run apps/system_status
```

For a persistent install, use `app-install` and `app-start` explicitly.

Triple-click returns Home through the normal foreground-app lifecycle.
