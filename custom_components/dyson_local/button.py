
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import CONF_NAME
from homeassistant.components.button import ButtonEntity

from typing import Optional


from . import DysonConfigEntry, DysonEntity

import logging

_LOGGER = logging.getLogger(__name__)


# Devices push state over MQTT; commands are not rate limited.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DysonConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dyson button from a config entry."""
    device = config_entry.runtime_data.device
    name = config_entry.data[CONF_NAME]


    entities = []

    if hasattr(device, "filter_life"):
        entities.append(DysonFilterResetButton(device, name))

    async_add_entities(entities)


class DysonFilterResetButton(DysonEntity, ButtonEntity):
    _attr_entity_category = EntityCategory.CONFIG

    @property
    def sub_name(self) -> Optional[str]:
        """Return the name of the Dyson button."""
        return "Reset Filter Life"

    @property
    def sub_unique_id(self) -> str:
        """Return the button's unique id."""
        return "reset-filter"

    def press(self) -> None:
        self._device.reset_filter()
