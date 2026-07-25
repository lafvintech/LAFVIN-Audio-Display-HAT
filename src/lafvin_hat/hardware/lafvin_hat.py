"""Public composition root for supported LAFVIN HAT hardware."""

from .native import NativeLafvinHatBoard


class LafvinHatBoard(NativeLafvinHatBoard):
    """The supported native Raspberry Pi LAFVIN HAT board.

    The public name intentionally remains small and stable for Runtime and
    external development drivers. It delegates platform, GPIO, SPI, display,
    button, LED, and backlight responsibilities to the modular components in
    :mod:`lafvin_hat.hardware.native`.
    """


__all__ = ["LafvinHatBoard"]
