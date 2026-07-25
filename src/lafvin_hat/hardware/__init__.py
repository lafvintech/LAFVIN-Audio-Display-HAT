"""Hardware boundaries for supported LAFVIN HAT devices."""

from .lafvin_hat import LafvinHatBoard
from .native import NativeLafvinHatBoard

__all__ = [
    "LafvinHatBoard",
    "NativeLafvinHatBoard",
]
