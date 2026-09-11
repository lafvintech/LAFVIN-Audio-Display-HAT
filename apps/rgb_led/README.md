# RGB LED

Bundled RGB lamp application. It drives the HAT RGB LED and keeps the LCD
cleared; the screen is not used as a control surface.

Modes:

- gradient: continuous rainbow cycle on the LED (default)
- palette: a static color from a fixed set

Controls:

- single click: leave gradient (if needed) and cycle the palette
- double click: return to the gradient cycle
- triple click: return Home

The LED turns off when the App exits.

Run during development:

```bash
lafvin-hat app run apps/rgb_led
```

For a persistent install, use `app-install` and `app-start` explicitly.
