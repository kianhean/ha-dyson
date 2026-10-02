"""Tests for HushJet Purifier Compact (HJ10 / 897) device support."""

from unittest.mock import MagicMock, patch

from custom_components.dyson_local.const import DEVICE_TYPE_HUSHJET


class TestHushJetConstants:
    """Test device type constant value."""

    def test_device_type_is_897(self):
        assert DEVICE_TYPE_HUSHJET == "897"


class TestHushJetCloudMapping:
    """Test that 897 / HJ10 / M4P product types resolve correctly."""

    def test_897_in_cloud_mapping(self):
        from custom_components.dyson_local.config_flow import (
            CLOUD_PRODUCT_TYPE_TO_DEVICE_TYPE,
        )

        assert CLOUD_PRODUCT_TYPE_TO_DEVICE_TYPE["897"] == DEVICE_TYPE_HUSHJET

    def test_m4p_in_cloud_mapping(self):
        from custom_components.dyson_local.config_flow import (
            CLOUD_PRODUCT_TYPE_TO_DEVICE_TYPE,
        )

        assert CLOUD_PRODUCT_TYPE_TO_DEVICE_TYPE["M4P"] == DEVICE_TYPE_HUSHJET

    def test_hj10_in_cloud_mapping(self):
        from custom_components.dyson_local.config_flow import (
            CLOUD_PRODUCT_TYPE_TO_DEVICE_TYPE,
        )

        assert CLOUD_PRODUCT_TYPE_TO_DEVICE_TYPE["HJ10"] == DEVICE_TYPE_HUSHJET

    def test_hushjet_in_device_type_names(self):
        from custom_components.dyson_local.config_flow import DEVICE_TYPE_NAMES

        assert DEVICE_TYPE_HUSHJET in DEVICE_TYPE_NAMES
        assert "HushJet" in DEVICE_TYPE_NAMES[DEVICE_TYPE_HUSHJET]


class TestHushJetGetDevice:
    """Test that the local get_device wrapper creates a DysonPureCool for 897."""

    @patch("custom_components.dyson_local._libdyson_get_device", return_value=None)
    def test_get_device_creates_pure_cool_for_hushjet(self, mock_get):
        from libdyson import DysonPureCool

        from custom_components.dyson_local import get_device

        device = get_device("SERIAL", "CRED", DEVICE_TYPE_HUSHJET)
        assert isinstance(device, DysonPureCool)
        assert device.serial == "SERIAL"

    @patch("custom_components.dyson_local._libdyson_get_device")
    def test_get_device_delegates_known_types(self, mock_get):
        sentinel = MagicMock()
        mock_get.return_value = sentinel

        from custom_components.dyson_local import get_device

        device = get_device("SERIAL", "CRED", "438")
        assert device is sentinel

    @patch("custom_components.dyson_local._libdyson_get_device", return_value=None)
    def test_get_device_returns_none_for_unknown(self, mock_get):
        from custom_components.dyson_local import get_device

        assert get_device("SERIAL", "CRED", "UNKNOWN") is None
