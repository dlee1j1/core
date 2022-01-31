"""Signal handling related helpers."""
import logging
import signal
import sys
from types import FrameType
from typing import Any, Optional

from homeassistant.const import RESTART_EXIT_CODE
from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import bind_hass

_LOGGER = logging.getLogger(__name__)


@callback
@bind_hass
def async_register_signal_handling(hass: HomeAssistant) -> None:
    """Register system signal handler for core."""
    if sys.platform != "win32":

        @callback
        def async_signal_handle(exit_code: int) -> None:
            """Wrap signal handling.

            * queue call to shutdown task
            * re-instate default handler
            """
            hass.loop.remove_signal_handler(signal.SIGTERM)
            hass.loop.remove_signal_handler(signal.SIGINT)
            hass.async_create_task(hass.async_stop(exit_code))

        try:
            hass.loop.add_signal_handler(signal.SIGTERM, async_signal_handle, 0)
        except ValueError:
            _LOGGER.warning("Could not bind to SIGTERM")

        try:
            hass.loop.add_signal_handler(signal.SIGINT, async_signal_handle, 0)
        except ValueError:
            _LOGGER.warning("Could not bind to SIGINT")

        try:
            hass.loop.add_signal_handler(
                signal.SIGHUP, async_signal_handle, RESTART_EXIT_CODE
            )
        except ValueError:
            _LOGGER.warning("Could not bind to SIGHUP")

    else:

        @callback
        def async_signal_handle(exit_code: int, frame: Optional[FrameType]) -> Any:
            """Wrap signal handling.

            * queue call to shutdown task
            * re-instate default handler
            """
            signal.signal(signal.SIGTERM, old_sigterm)
            signal.signal(signal.SIGINT, old_sigint)
            hass.async_create_task(hass.async_stop(exit_code))
            return True

        old_sigterm: Any = async_signal_handle
        old_sigint: Any = async_signal_handle

        try:
            old_sigterm = signal.signal(signal.SIGTERM, async_signal_handle)
        except ValueError:
            _LOGGER.warning("Could not bind to SIGTERM")

        try:
            old_sigint = signal.signal(signal.SIGINT, async_signal_handle)
        except ValueError:
            _LOGGER.warning("Could not bind to SIGINT")
