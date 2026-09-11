# Dino Runner

Single-button pixel dinosaur runner rendered with the app-facing Raw Frame
Toolkit. The source directory and stable App ID remain `apps/one_button_jump/`
and `dev.lafvin.jump` for installation compatibility.

The visual style is inspired by offline endless runners, using original
project-drawn dinosaur, cactus, and cloud sprites rather than browser or Chrome
assets.

The game provides three states:

- Ready: press the button to start with an immediate jump.
- Running: press while grounded to jump over randomized cactus obstacles.
- Game Over: single-click to retry after the short input guard.

Triple-click returns Home through the normal Runtime foreground-App lifecycle.
Running uses immediate `button.raw_pressed` events so jumping does not wait for
gesture disambiguation. The Game Over retry uses `button.single_clicked`, which
keeps a triple-click exit from accidentally starting another round.

Score increases when a cactus is passed. The current process keeps the highest
score across retries. Movement speed is 130% of the base speed from score 15 and
150% from score 30. The jump arc is deliberately tall and lasts for more than
one second at the base speed so the dinosaur can clear the portrait playfield's
larger cactus silhouettes.

The App reuses one `lafvin_hat.ui.Canvas` for Toolkit theme, fonts, RGB565
encoding, and frame presentation. Physics, collision boxes, animation timing,
and pixel sprites remain App-owned.

Run during development:

```bash
lafvin-hat app run apps/one_button_jump
```

For a persistent install:

```bash
lafvin-hat app install apps/one_button_jump
lafvin-hat app start dev.lafvin.jump
```
