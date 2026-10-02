"""Camera platform for Dyson cloud."""
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.camera import Camera
from homeassistant.helpers.device_registry import DeviceInfo

from libdyson.const import DEVICE_TYPE_360_EYE
from libdyson.cloud.cloud_360_eye import DysonCloud360Eye
from libdyson.cloud import DysonDeviceInfo

from . import DysonConfigEntry
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=30)


# The cloud map is fetched one entity at a time.
PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DysonConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Dyson fan from a config entry."""
    account = config_entry.runtime_data.account
    devices = config_entry.runtime_data.devices
    entities = []
    for device in devices:
        if device.product_type not in [DEVICE_TYPE_360_EYE]:
            continue
        entities.append(DysonCleaningMapEntity(
            DysonCloud360Eye(account, device.serial),
            device,
        ))
    async_add_entities(entities, True)


class DysonCleaningMapEntity(Camera):
    """Dyson vacuum cleaning map entity."""

    _attr_has_entity_name = True
    _attr_name = "Cleaning Map"

    def __init__(self, device: DysonCloud360Eye, device_info: DysonDeviceInfo):
        super().__init__()
        self._device = device
        self._device_info = device_info
        self._last_cleaning_task = None
        self._image = None

    @property
    def unique_id(self) -> str:
        """Return entity unique id."""
        return self._device_info.serial

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info of the entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_info.serial)},
            name=self._device_info.name,
            manufacturer="Dyson",
            model=self._device_info.product_type,
            sw_version=self._device_info.version,
        )

    @property
    def icon(self) -> str:
        """Return entity icon."""
        return "mdi:map"

    def camera_image(self, width=None, height=None):
        """Return cleaning map. Width and height are ignored."""
        return self._image

    def update(self):
        """Check for map update."""
        _LOGGER.debug("Running cleaning map update for %s", self._device_info.name)
        cleaning_tasks = self._device.get_cleaning_history()

        last_task = None
        for task in cleaning_tasks:
            if task.area > 0.0:
                # Skip cleaning tasks with 0 area, map not available
                last_task = task
                break
        if last_task is None:
            _LOGGER.debug("No cleaning history found.")
            self._last_cleaning_task = None
            return

        if last_task == self._last_cleaning_task:
            _LOGGER.debug("Cleaning task not changed. Skip update.")
            return
        self._last_cleaning_task = last_task
        self._image = self._device.get_cleaning_map(
            self._last_cleaning_task.cleaning_id
        )
