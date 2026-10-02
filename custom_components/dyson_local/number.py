"""Number platform for Dyson."""

from typing import Callable, Optional

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
)

from libdyson.const import ENVIRONMENTAL_OFF, MessageType

from .const import DATA_COORDINATORS, DATA_DEVICES, DOMAIN

from . import DysonEntity

import logging

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry, async_add_entities: Callable
) -> None:
    """Set up Dyson number entities from a config entry."""
    device = hass.data[DOMAIN][DATA_DEVICES][config_entry.entry_id]
    coordinator = hass.data[DOMAIN][DATA_COORDINATORS][config_entry.entry_id]
    name = config_entry.data[CONF_NAME]

    entities = [
        DysonAirflowSpeedNumber(device, name),
        DysonSleepTimerNumber(coordinator, device, name),
    ]

    async_add_entities(entities)


class DysonAirflowSpeedNumber(DysonEntity, NumberEntity):
    """Dyson fan airflow speed."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:fan"
    _attr_mode = NumberMode.SLIDER
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1

    @property
    def sub_name(self) -> str:
        """Return the name of the number."""
        return "Airflow Speed"

    @property
    def sub_unique_id(self):
        """Return the number's unique id."""
        return "airflow_speed"

    @property
    def native_value(self) -> Optional[int]:
        """Return the current speed, or None while the device reports auto."""
        return self._device.speed

    def set_native_value(self, value: float) -> None:
        """Set a manual speed, leaving auto mode like the fan entity does."""
        self._device.set_speed(int(value))
        self._device.disable_auto_mode()


class DysonSleepTimerNumber(CoordinatorEntity, DysonEntity, NumberEntity):
    """Dyson fan sleep timer, where 0 turns the timer off."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:timer-outline"
    _attr_mode = NumberMode.BOX
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_native_min_value = 0
    _attr_native_max_value = 540
    _attr_native_step = 1
    _MESSAGE_TYPE = MessageType.ENVIRONMENTAL

    def __init__(self, coordinator: DataUpdateCoordinator, device, name):
        """Initialize the number entity."""
        CoordinatorEntity.__init__(self, coordinator)
        DysonEntity.__init__(self, device, name)

    @property
    def sub_name(self) -> str:
        """Return the name of the number."""
        return "Sleep Timer"

    @property
    def sub_unique_id(self):
        """Return the number's unique id."""
        return "sleep_timer"

    @property
    def native_value(self) -> Optional[int]:
        """Return the minutes remaining, or 0 when the timer is off."""
        value = self._device.sleep_timer
        if value == ENVIRONMENTAL_OFF:
            return 0
        if value is None or value < 0:
            return None
        return value

    async def async_set_native_value(self, value: float) -> None:
        """Set the sleep timer in minutes."""
        minutes = int(value)
        if minutes == 0:
            await self.hass.async_add_executor_job(self._device.disable_sleep_timer)
        else:
            await self.hass.async_add_executor_job(
                self._device.set_sleep_timer, minutes
            )
        # The timer is only reported in environmental data, so poll it now
        # instead of waiting for the next scheduled update.
        await self.coordinator.async_request_refresh()
