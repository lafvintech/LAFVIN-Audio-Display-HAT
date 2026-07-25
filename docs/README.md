# LAFVIN Audio Display HAT Documentation

This is the documentation entry point for the current public checkout. The
guides below describe the supported Runtime, application-development,
simulator, deployment, and hardware-profile workflows.

## Current Documentation

| Need | Read |
|---|---|
| Project overview, Raspberry Pi installation, deployment, recovery, and common commands | [Project README](../README.md) |
| Local development and first-party App structure | [Application Development Guide](APP_DEVELOPMENT.md) |
| Toolkit components and visual rules | [UI Toolkit Guide](UI_GUIDE.md) |
| Simulator use and its limits | [Simulator Guide](SIMULATOR.md) |
| WM8960 profile provenance and support boundary | [Profile Record](../hardware/lafvin_hat/wm8960/v2/PROFILE.md) and [Third-Party Notices](THIRD_PARTY_NOTICES.md) |
| Public release changes | [Changelog](../CHANGELOG.md) |

The repository root [README](../README.md) is the canonical Raspberry Pi
installation, deployment, recovery, and command reference. The documents
above provide the other supported workflows.

## Naming

The product name is **LAFVIN Audio Display HAT**. Stable software interfaces
retain the `lafvin-hat` command and service identifier and the `lafvin_hat`
Python package name.

## Maintenance Rules

1. Update current guides when a supported command, path, installation step, or
   user-visible behavior changes.
2. Keep `docs/THIRD_PARTY_NOTICES.md`, hardware-profile records, and bundled
   component licenses aligned with the files distributed by the project.
3. Remove a document only after confirming it has no current documentation,
   deployment, source, or test reference.
4. Keep secrets, device logs, and recorded user audio out of documentation and
   Git. Show variable names and redacted examples only.
