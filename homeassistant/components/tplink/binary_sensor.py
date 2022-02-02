"""This is the aggressive updater for tplink."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from kasa import Discover, SmartDevice
import voluptuous as vol

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MIN_TIME_BETWEEN_DISCOVERS

ATTR_CONFIG = "config"
CONF_AGGRESSIVE = "aggressive-update-via-udp-broadcast"
CONF_DISCOVERY_BROADCAST_DOMAIN = "discovery-broadcast-domain"

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(CONF_AGGRESSIVE, default=True): cv.boolean,
                vol.Optional(
                    CONF_DISCOVERY_BROADCAST_DOMAIN, default="255.255.255.255"
                ): cv.string,
            }
        )
    },
)

SCAN_INTERVAL = MIN_TIME_BETWEEN_DISCOVERS


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the UDP poller."""
    config_data = hass.data[DOMAIN].get(ATTR_CONFIG)
    broadcast_domain = "255.255.255.255"
    if config_data is not None:
        be_aggressive = config_data.get(CONF_AGGRESSIVE)
        if not be_aggressive:
            return
        broadcast_domain = config_data.get(
            CONF_DISCOVERY_BROADCAST_DOMAIN, broadcast_domain
        )

    async def _async_kick_off(*_: Any) -> None:
        # add the updater
        hass.data[DOMAIN][CONF_DISCOVERY_BROADCAST_DOMAIN] = broadcast_domain
        updater: Entity = TPLinkUpdater(broadcast_domain)
        async_add_entities([updater])
        hass.data[DOMAIN]["updater"] = updater

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_kick_off)
    return


class TPLinkUpdater(BinarySensorEntity):
    """Update TPLimk SmartBulb and SmartSwitches entities using the Kasa discovery protocol."""

    def __init__(self, broadcast_domain: str) -> None:
        """Initialize me."""
        self._broadcast_domain = broadcast_domain
        self._last_updated = datetime.min
        self._start_time = datetime.now()

    @property
    def name(self) -> str:
        """Return the name of the binary sensor, if any."""
        return "TPLinkUpdater"

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return "tplink-updater"

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        if self._last_updated == datetime.min:
            return False
        return True

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        avail = self._last_updated != datetime.min
        return avail

    def schedule_discovery(self) -> None:
        """Ask HASS to schedule a single discovery call."""
        self.hass.async_create_task(
            Discover.discover(
                target=self._broadcast_domain,
                on_discovered=self.update_from_discovery,
                discovery_packets=1,
            )
        )

    async def async_update(self) -> None:
        """Kicks off another set of discoveries if it's been a while. Otherwise, it waits for the next tick."""
        time = datetime.now()

        # kick off the discovery cycle but we wait for the devices to have gone silent for a while
        if time - self._last_updated > MIN_TIME_BETWEEN_DISCOVERS:
            self.schedule_discovery()

    async def update_from_discovery(self, device: SmartDevice) -> None:
        """Tell entities that their devices got an update."""
        self._last_updated = datetime.now()
        hass_data: dict[str, Entity] = self.hass.data[DOMAIN]
        entity: Entity | None = hass_data.get(device.device_id)
        if entity is None:
            # we can kick off the create entity from here
            return
        entity.async_write_ha_state()
        if device.is_strip:
            for plug in device.children:
                self.update_from_discovery(plug)
