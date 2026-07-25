# One Button Jump

The M3 sample game validates the Raw Frame SDK, explicit frame commits,
foreground ownership, and button events without directly accessing display or
GPIO hardware.

The game draws its own frames instead of using the UI toolkit because it is an
animation-heavy app with custom timing and collision state.

Run during development:

```bash
lafvin-hat app run apps/one_button_jump
```

For a persistent install:

```bash
lafvin-hat app install apps/one_button_jump
lafvin-hat app start dev.lafvin.jump
```

Press the simulator or hardware button to jump. After collision, the in-game
menu can continue or exit.
