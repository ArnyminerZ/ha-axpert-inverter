import logging
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.service_info.usb import UsbServiceInfo

from .const import (
    DOMAIN,
    CONF_BACKEND,
    CONF_DEVICE_PATH,
    CONF_DEVICE_PHYS,
    CONF_SCAN_INTERVAL,
    BACKEND_HIDRAW,
    BACKEND_USB,
    DEFAULT_DEVICE_PATH,
    DEFAULT_SCAN_INTERVAL,
)
from .axpert import AxpertInverter
from .hidraw import HidrawDevice, find_hidraw_devices

_LOGGER = logging.getLogger(__name__)


def _probe(backend: str, path: str, phys: str | None) -> str | None:
    """Talk to the inverter (blocking). Returns its serial number if it answers QID.

    Raises if the inverter can't be reached or doesn't answer QPIGS.
    """
    inverter = AxpertInverter(path, backend=backend, device_phys=phys)
    if not inverter.get_general_status():
        raise ValueError("Empty response from QPIGS during validation")
    try:
        return inverter.get_device_id() or None
    except Exception:  # noqa: BLE001 - QID is not supported by all firmware
        return None


async def _async_validate(hass: HomeAssistant, user_input: dict) -> tuple[dict, str | None, str | None]:
    """Validate the input. Returns (data to store, serial, error key)."""
    data = dict(user_input)
    path = data.get(CONF_DEVICE_PATH) or DEFAULT_DEVICE_PATH
    data[CONF_DEVICE_PATH] = path
    data.setdefault(CONF_BACKEND, BACKEND_HIDRAW)

    # Remember the stable USB port so the device is found again if hidrawN renumbers
    devices: list[HidrawDevice] = await hass.async_add_executor_job(find_hidraw_devices)
    phys = next((d.phys for d in devices if d.path == path and d.phys), None)
    if phys:
        data[CONF_DEVICE_PHYS] = phys
    else:
        data.pop(CONF_DEVICE_PHYS, None)

    try:
        serial = await hass.async_add_executor_job(_probe, data[CONF_BACKEND], path, phys)
    except Exception as err:  # noqa: BLE001
        _LOGGER.error("Failed to connect to the inverter: %s", err)
        return data, None, "cannot_connect"
    return data, serial, None


async def _async_schema(hass: HomeAssistant, backend: str, path: str | None, scan_interval: int) -> vol.Schema:
    devices: list[HidrawDevice] = await hass.async_add_executor_job(find_hidraw_devices)
    options = [SelectOptionDict(value=d.path, label=d.label) for d in devices]
    default_path = path or (devices[0].path if devices else DEFAULT_DEVICE_PATH)

    return vol.Schema({
        vol.Required(CONF_BACKEND, default=backend): SelectSelector(
            SelectSelectorConfig(
                options=[BACKEND_HIDRAW, BACKEND_USB],
                mode=SelectSelectorMode.DROPDOWN,
                translation_key=CONF_BACKEND,
            )
        ),
        vol.Required(CONF_DEVICE_PATH, default=default_path): SelectSelector(
            SelectSelectorConfig(options=options, custom_value=True, mode=SelectSelectorMode.DROPDOWN)
        ),
        vol.Optional(CONF_SCAN_INTERVAL, default=scan_interval): vol.All(vol.Coerce(int), vol.Range(min=1)),
    })


class AxpertConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Axpert Inverter."""

    VERSION = 1

    async def async_step_usb(self, discovery_info: UsbServiceInfo) -> FlowResult:
        """Handle USB discovery (the inverter's VID/PID matched)."""
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        return await self.async_step_usb_confirm()

    async def async_step_usb_confirm(self, user_input=None) -> FlowResult:
        """Ask for confirmation before configuring a discovered inverter."""
        if user_input is not None:
            return await self.async_step_user()
        return self.async_show_form(step_id="usb_confirm")

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            data, serial, error = await _async_validate(self.hass, user_input)
            if error is None:
                unique_id = serial or data.get(CONF_DEVICE_PHYS)
                if unique_id:
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Axpert Inverter ({data[CONF_DEVICE_PATH]})",
                    data=data,
                )
            errors["base"] = error

        user_input = user_input or {}
        schema = await _async_schema(
            self.hass,
            user_input.get(CONF_BACKEND, BACKEND_HIDRAW),
            user_input.get(CONF_DEVICE_PATH),
            user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return AxpertOptionsFlowHandler()


class AxpertOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Axpert Inverter."""

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Manage the options."""
        errors = {}

        if user_input is not None:
            data, _serial, error = await _async_validate(self.hass, user_input)
            if error is None:
                return self.async_create_entry(title="", data=data)
            errors["base"] = error

        entry = self.config_entry

        def current(key, default=None):
            return entry.options.get(key, entry.data.get(key, default))

        user_input = user_input or {}
        # Entries created before the hidraw backend existed keep using pyusb until changed here
        schema = await _async_schema(
            self.hass,
            user_input.get(CONF_BACKEND, current(CONF_BACKEND, BACKEND_USB)),
            user_input.get(CONF_DEVICE_PATH, current(CONF_DEVICE_PATH, DEFAULT_DEVICE_PATH)),
            user_input.get(CONF_SCAN_INTERVAL, current(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
