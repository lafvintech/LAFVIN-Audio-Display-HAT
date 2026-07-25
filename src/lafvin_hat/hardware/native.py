"""Native LAFVIN HAT board composition for supported Raspberry Pi hardware."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable

from .backlight import Backlight
from .button import Button
from .display import St7789Display
from .gpio import GpioController
from .rgb_led import RgbLed
from .rpi_platform import RaspberryPiPlatform
from .spi import SpiTransport


class NativeLafvinHatBoard:
    """Native board assembled from modular LAFVIN HAT hardware components."""

    profile_name = "lafvin-hat-rpi"
    implementation = "lafvin-native-rpi"

    LCD_DC_PIN = 13
    LCD_RESET_PIN = 7
    BACKLIGHT_PIN = 15
    RGB_RED_PIN = 22
    RGB_GREEN_PIN = 18
    RGB_BLUE_PIN = 16
    BUTTON_PIN = 11

    def __init__(
        self,
        *,
        platform: RaspberryPiPlatform | None = None,
        gpio: GpioController | None = None,
        spi: SpiTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.platform = platform or RaspberryPiPlatform.detect()
        self._gpio = gpio or GpioController(self.platform)
        self._spi = spi
        self.display: St7789Display | None = None
        self.button: Button | None = None
        self.led: RgbLed | None = None
        self.backlight: Backlight | None = None
        self._closed = False

        try:
            dc = self._gpio.request_output(self.LCD_DC_PIN, consumer="lafvin-lcd")
            reset = self._gpio.request_output(
                self.LCD_RESET_PIN,
                consumer="lafvin-lcd",
            )
            backlight_line = self._gpio.request_output(
                self.BACKLIGHT_PIN,
                consumer="lafvin-backlight",
            )
            red = self._gpio.request_output(self.RGB_RED_PIN, consumer="lafvin-rgb")
            green = self._gpio.request_output(
                self.RGB_GREEN_PIN,
                consumer="lafvin-rgb",
            )
            blue = self._gpio.request_output(
                self.RGB_BLUE_PIN,
                consumer="lafvin-rgb",
            )
            button_line = self._gpio.request_input(
                self.BUTTON_PIN,
                consumer="lafvin-button",
            )
            if self._spi is None:
                self._spi = SpiTransport(
                    bus=self.platform.spi_bus,
                    chip_select=self.platform.spi_chip_select,
                    speed_hz=self.platform.spi_speed_hz,
                )
            self.display = St7789Display(
                self._spi,
                data_command_line=dc,
                reset_line=reset,
                sleep=sleep,
            )
            self.led = RgbLed(red, green, blue)
            self.backlight = Backlight(backlight_line)
            self.button = Button(button_line)
            self.backlight.set(0)
            self.display.initialize()
            self.display.fill_rgb565(0)
            self.button.start()
        except Exception:
            self.cleanup()
            raise

    def cleanup(self) -> None:
        if self._closed:
            return
        self._closed = True
        # Stop all writers/readers before their GPIO lines are released.
        for component in (self.button, self.backlight, self.led):
            if component is not None:
                with contextlib.suppress(Exception):
                    component.close() if hasattr(component, "close") else component.stop()
        if self._spi is not None:
            with contextlib.suppress(Exception):
                self._spi.close()
        with contextlib.suppress(Exception):
            self._gpio.close()
