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
- RGB565 Raw Frame rendering through an HTML Canvas

The compatibility declarative UI path uses the same validated UI model as the
Pillow device renderer. Applications therefore do not contain simulator-specific
UI code.

Raw Frame applications write the same RGB565 buffer consumed by the LAFVIN HAT
hardware backend. The simulator fetches the committed frame only when its
sequence changes.

Start it with:

```bash
lafvin-hat runtime start
```

Use a different web port when needed:

```bash
lafvin-hat runtime start --simulator-port 18080
```
