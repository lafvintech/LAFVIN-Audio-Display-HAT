# Volume

Bundled Runtime volume control application. It is a simple interactive Raw
Frame UI toolkit page.

Controls:

- single click: switch between `-10%` and `+10%`
- double click: apply the selected adjustment
- triple click: return Home

After an adjustment, the App waits half a second and plays a short low-to-high
preview through Runtime audio ownership. Another adjustment resets that timer
and stops an in-progress preview, so rapid changes do not queue sounds.

Click sequences are recognized by the Runtime gesture service. The App consumes
the resulting single/double events so a triple-click exit cannot accidentally
apply another volume adjustment on a slower device.

Run during development:

```bash
lafvin-hat app run apps/system_volume
```

For a persistent install, use `app-install` and `app-start` explicitly.
