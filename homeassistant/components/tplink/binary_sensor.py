"""This is the aggressive updater for tplink."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any

from kasa import Discover, SmartDevice
import voluptuous as vol

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import DOMAIN, MIN_TIME_BETWEEN_DISCOVERS
from .entity import CoordinatedTPLinkEntity

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


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the UDP poller."""
    _LOGGER.info("Updater Binary Sensor Platform setup called")
    data: dict[str, Any] = hass.data[DOMAIN]

    config_data = data.get(ATTR_CONFIG)
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
        data[CONF_DISCOVERY_BROADCAST_DOMAIN] = broadcast_domain
        updater: Entity = TPLinkUpdater(broadcast_domain)
        async_add_entities([updater])

    #       data[DOMAIN]["updater"] = updater

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _async_kick_off)


class TPLinkUpdater(BinarySensorEntity):
    """Update TPLink SmartBulb and SmartSwitches entities using the Kasa discovery protocol."""

    def __init__(self, broadcast_domain: str) -> None:
        """Initialize me."""
        self._broadcast_domain = broadcast_domain
        self._last_updated = datetime.min

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
        _LOGGER.debug("Creating a discovery call")
        self.hass.async_create_task(
            Discover.discover(
                target=self._broadcast_domain,
                on_discovered=self.update_from_discovery,
                discovery_packets=1,
            )
        )

    async def async_update(self) -> None:
        """Kicks off another set of discoveries."""
        if CoordinatedTPLinkEntity.has_any_entity():
            self.schedule_discovery()

    async def update_from_discovery(self, device: SmartDevice) -> None:
        """Tell entities that their devices got an update."""
        self._last_updated = datetime.now()
        entity: Entity | None = CoordinatedTPLinkEntity.get_entity(device.device_id)
        if entity is None:
            # we can kick off the create entity from here
            return
        _LOGGER.info("Updating entity %s", entity.name)
        entity.async_write_ha_state()
        if device.is_strip:
            for plug in device.children:
                self.update_from_discovery(plug)
