# Web Simulator

The simulator is a formal Device Runtime backend, not a separate
Chatbot-specific implementation.

The simulator currently provides:

- a browser control panel at `http://127.0.0.1:17880`
- 240x280 display dimensions
- physical button press and release injection
- RGB LED and backlight state
- battery and network state injection
- deterministic IPC controls for integration tests
- web rendering for the declarative UI model
- synchronized UI revision and RGB565 frame sequence state
- one 240x280 HTML Canvas for Runtime and application RGB565 output, presented
  through a smooth device-pixel-ratio-aware HiDPI backing store
- single-click, double-click, and triple-click shortcuts
- a raw press-and-hold control for physical-button timing tests

The Runtime renders compatibility declarative views with the Pillow device
renderer before presenting them to the simulator Canvas. Applications therefore
do not contain simulator-specific UI code, and the browser does not maintain a
second HTML implementation of the device UI.

Raw Frame applications write the same RGB565 buffer consumed by the LAFVIN HAT
hardware backend. The browser checks Raw Frame output at a 30 FPS target for
animation and video, while declarative screens refresh when their frame sequence
changes.

The incoming frame remains exactly 240x280. The browser first writes it to a
native-size off-screen Canvas, then smoothly draws it into a visible backing
store sized for `window.devicePixelRatio`. The visible CSS size remains 240x280,
so HiDPI rendering improves desktop presentation without changing the Runtime
frame protocol or claiming additional device detail.

Use the gesture shortcuts for normal navigation. Use the raw button when testing
press duration, release handling, or the Runtime gesture recognizer itself. The
shortcut controls still generate timed raw press and release events, so their
single-, double-, and triple-click results follow the normal Runtime path.
The triple-click shortcut is disabled on Home, where the product gesture model
resolves the first two clicks as a Home confirmation instead of an exit gesture.

Start it with:

```bash
lafvin-hat runtime start
```

Use a different web port when needed:

```bash
lafvin-hat runtime start --simulator-port 18080
```
