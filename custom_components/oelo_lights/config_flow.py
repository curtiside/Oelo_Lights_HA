"""Config flow for Oelo Lights integration.

Handles initial setup (IP validation) and multi-step options flow.

Config Flow Steps:
- user: Initial setup - IP address entry and validation
- reconfigure: Reconfigure existing controller IP address
- Options flow (multi-step):
  - init: Basic settings (zones, polling)
  - spotlight: Spotlight plan settings (LED indices, max LEDs)
  - verification: Command verification settings
  - advanced: Advanced settings (timeouts, debug logging)

IP Validation:
- Format check (IPv4)
- Connection test to /getController endpoint
- Response validation (JSON array expected)

Options Flow:
Multi-step flow organized by category. Each step collects related settings:
1. Basic: Zones (multi-select), poll interval, auto poll
2. Spotlight: Max LEDs, spotlight plan lights (comma-delimited LED indices)
3. Verification: Verify commands toggle, retries, delay, timeout
4. Advanced: Command timeout, debug logging

Example Usage:
    # Initial setup via UI:
    Settings → Devices & Services → Add Integration → oelo_lights_ha
    # Enter IP address → Submit
    
    # Configure options:
    Settings → Devices & Services → oelo_lights_ha → Configure
    # Follow multi-step wizard

Troubleshooting:
- Invalid IP: Check format (IPv4), ensure controller is online
- Cannot connect: Verify network connectivity, firewall rules, controller on same network
- Options not saving: Ensure all steps completed, check logs for errors
"""

from __future__ import annotations
import logging
from typing import Any
import voluptuous as vol
import ipaddress
import asyncio  
import aiohttp  

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow, ConfigEntry
from homeassistant.const import CONF_IP_ADDRESS
from homeassistant.helpers.aiohttp_client import async_get_clientsession 
from homeassistant.core import HomeAssistant, callback
from homeassistant import data_entry_flow
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_ZONES,
    CONF_POLL_INTERVAL,
    CONF_AUTO_POLL,
    CONF_COMMAND_TIMEOUT,
    CONF_DEBUG_LOGGING,
    CONF_MAX_LEDS,
    CONF_SPOTLIGHT_PLAN_LIGHTS,
    CONF_VERIFY_COMMANDS,
    CONF_VERIFICATION_RETRIES,
    CONF_VERIFICATION_DELAY,
    CONF_VERIFICATION_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_AUTO_POLL,
    DEFAULT_COMMAND_TIMEOUT,
    DEFAULT_DEBUG_LOGGING,
    DEFAULT_MAX_LEDS,
    DEFAULT_SPOTLIGHT_PLAN_LIGHTS,
    DEFAULT_VERIFY_COMMANDS,
    DEFAULT_VERIFICATION_RETRIES,
    DEFAULT_VERIFICATION_DELAY,
    DEFAULT_VERIFICATION_TIMEOUT,
    DEFAULT_ZONES,
)
from .pattern_utils import normalize_led_indices

_LOGGER = logging.getLogger(__name__)

class CannotConnect(Exception):
    """Exception raised when connection to device cannot be established."""
    pass

class InvalidIP(Exception):
    """Exception raised for invalid IP address format."""
    pass


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, str]:
    """Validate user input allows us to connect.
    
    Validates IP address format and tests connection to controller.
    
    Args:
        hass: Home Assistant instance
        data: User input dict containing CONF_IP_ADDRESS
        
    Returns:
        Dict with "title" key for config entry
        
    Raises:
        InvalidIP: IP format invalid or missing
        CannotConnect: Connection failed or device not Oelo controller
        
    Example:
        try:
            info = await validate_input(hass, {"ip_address": "192.168.1.100"})
        except InvalidIP:
            # Handle invalid IP
        except CannotConnect:
            # Handle connection failure
    """

    ip = data.get(CONF_IP_ADDRESS)
    if not ip:
        raise InvalidIP("No IP address provided.")

    try:
        ipaddress.ip_address(ip)
    except ValueError:
        _LOGGER.debug("Invalid IP address format: %s", ip)
        raise InvalidIP("Invalid IP address format.")

    session = async_get_clientsession(hass)
    controller_url = f"http://{ip}/getController"

    try:
        _LOGGER.debug("Attempting to connect to Oelo controller at %s", controller_url)
        timeout = aiohttp.ClientTimeout(total=10, connect=5)
        async with session.get(controller_url, timeout=timeout) as response:
            if response.status == 200:
                try:
                    # Try to parse response as JSON to verify it's an Oelo controller
                    data = await response.json(content_type=None)
                    if isinstance(data, list):
                        _LOGGER.debug("Successfully connected to Oelo controller at %s", ip)
                        return {"title": "oelo_lights_ha"} 
                    else:
                        _LOGGER.warning("Unexpected response format from %s", ip)
                        raise CannotConnect("Device responded but doesn't appear to be an Oelo controller")
                except (aiohttp.ContentTypeError, ValueError) as err:
                    _LOGGER.warning("Invalid JSON response from %s: %s", ip, err)
                    raise CannotConnect("Device responded but doesn't appear to be an Oelo controller")
            else:
                _LOGGER.warning(
                    "Failed to connect to Oelo controller at %s - HTTP Status: %s",
                    ip,
                    response.status,
                )
                raise CannotConnect(f"Controller responded with status {response.status}")

    except (aiohttp.ClientConnectorError, aiohttp.ClientError) as err:
        _LOGGER.warning(
            "Failed to connect to Oelo controller at %s: %s", ip, err
        )
        raise CannotConnect(f"Could not connect to the controller at {ip}. Check IP address and ensure device is online.")
    except (asyncio.TimeoutError, aiohttp.ServerTimeoutError) as err:
        _LOGGER.warning("Timeout connecting to Oelo controller at %s: %s", ip, err)
        raise CannotConnect(f"Connection to the controller at {ip} timed out.")
    except Exception as exc:
        _LOGGER.exception("Unexpected error validating Oelo controller at %s: %s", ip, exc)
        raise 


STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_IP_ADDRESS): str, 
})

class OeloLightsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle config flow for Oelo Lights integration.
    
    Manages initial setup and reconfiguration flows.
    """

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get options flow handler.
        
        Args:
            config_entry: Configuration entry to configure
            
        Returns:
            OptionsFlowHandler instance
        """
        return OeloLightsOptionsFlowHandler(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
                await self.async_set_unique_id(user_input[CONF_IP_ADDRESS], raise_on_progress=False)
                self._abort_if_unique_id_configured()

                # Set default options
                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                    options={
                        CONF_ZONES: DEFAULT_ZONES,
                        CONF_POLL_INTERVAL: DEFAULT_POLL_INTERVAL,
                        CONF_AUTO_POLL: DEFAULT_AUTO_POLL,
                        CONF_COMMAND_TIMEOUT: DEFAULT_COMMAND_TIMEOUT,
                        CONF_DEBUG_LOGGING: DEFAULT_DEBUG_LOGGING,
                        CONF_MAX_LEDS: DEFAULT_MAX_LEDS,
                        CONF_SPOTLIGHT_PLAN_LIGHTS: DEFAULT_SPOTLIGHT_PLAN_LIGHTS,
                        CONF_VERIFY_COMMANDS: DEFAULT_VERIFY_COMMANDS,
                        CONF_VERIFICATION_RETRIES: DEFAULT_VERIFICATION_RETRIES,
                        CONF_VERIFICATION_DELAY: DEFAULT_VERIFICATION_DELAY,
                        CONF_VERIFICATION_TIMEOUT: DEFAULT_VERIFICATION_TIMEOUT,
                    }
                )

            except InvalidIP:
                errors["base"] = "invalid_ip"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except data_entry_flow.AbortFlow:
                raise
            except Exception: 
                _LOGGER.exception("Unexpected exception during user step")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"error_message": errors.get("base", "")} 
        )


    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
        ) -> ConfigFlowResult:
        """Allow reconfiguration of an existing config entry."""
        errors: dict[str, str] = {}
        config_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        
        if config_entry is None:
            _LOGGER.error("Config entry not found for reconfiguration")
            return self.async_abort(reason="entry_not_found")

        if user_input is not None:

            current_data = {**config_entry.data, **user_input}
            try:
                await validate_input(self.hass, current_data)

                if config_entry.data.get(CONF_IP_ADDRESS) != user_input.get(CONF_IP_ADDRESS):
                     _LOGGER.debug("Oelo controller IP changed from %s to %s",
                                   config_entry.data.get(CONF_IP_ADDRESS),
                                   user_input.get(CONF_IP_ADDRESS))
            
                     if self._async_current_entries(): 
                         new_ip = user_input.get(CONF_IP_ADDRESS)
                         if new_ip:
                             existing_entry = await self.async_set_unique_id(new_ip, raise_on_progress=False)
                             if existing_entry and existing_entry.entry_id != config_entry.entry_id:
                                  errors["base"] = "reconfigure_failed_duplicate_ip"
                                  return self.async_show_form(
                                      step_id="reconfigure",
                                      data_schema=vol.Schema({vol.Required(CONF_IP_ADDRESS, default=user_input.get(CONF_IP_ADDRESS)): str}),
                                      errors=errors,
                                      description_placeholders={"ip_address": user_input.get(CONF_IP_ADDRESS)}
                                  )

                     return self.async_update_reload_and_abort(
                         config_entry,
                         unique_id=user_input.get(CONF_IP_ADDRESS), 
                         data=current_data,
                         reason="reconfigure_successful",
                     )
                else:
                     _LOGGER.debug("Oelo controller IP address unchanged during reconfigure.")
                     return self.async_abort(reason="reconfigure_successful")


            except InvalidIP:
                errors["base"] = "invalid_ip"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected exception during reconfigure step")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_IP_ADDRESS, default=config_entry.data.get(CONF_IP_ADDRESS)): str}),
            errors=errors,
        )


class OeloLightsOptionsFlowHandler(OptionsFlow):
    """Handle multi-step options flow for Oelo Lights.
    
    Organizes settings into logical steps: Basic → Spotlight → Verification → Advanced.
    """

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialize options flow.
        
        Args:
            config_entry: Configuration entry being configured
        """
        super().__init__()
        self._config_entry = config_entry
        self._options: dict[str, Any] = {}
    
    @property
    def config_entry(self) -> ConfigEntry:
        """Return config entry."""
        return self._config_entry

    def _get_spotlight_plan_lights_display(self, lights_str: str, max_leds: int = DEFAULT_MAX_LEDS) -> str:
        """Format spotlight plan lights for display.
        
        Normalizes and formats LED indices string. Truncates long lists.
        
        Args:
            lights_str: Comma-delimited LED indices string
            max_leds: Maximum LEDs for validation
            
        Returns:
            Formatted display string (e.g., "1,2,3,4" or "1,2,3,...,40 total")
        """
        if not lights_str:
            return "None"
        normalized = normalize_led_indices(lights_str, max_leds)
        if not normalized:
            return "None"
        indices = normalized.split(",")
        if len(indices) <= 10:
            return normalized
        return f"{','.join(indices[:10])},... ({len(indices)} total)"

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Basic settings step: zones, polling.
        
        Collects: zones (multi-select), poll interval, auto poll.
        Proceeds to spotlight step on submit.
        """
        if user_input is not None:
            self._options.update(user_input)
            # Convert zone strings to integers
            if CONF_ZONES in user_input:
                zones = user_input[CONF_ZONES]
                if isinstance(zones, list):
                    self._options[CONF_ZONES] = [int(z) for z in zones if str(z).isdigit()]
                elif isinstance(zones, str) and zones.isdigit():
                    self._options[CONF_ZONES] = [int(zones)]
            return await self.async_step_spotlight()

        options = self.config_entry.options
        self._options = dict(options)
        
        # Convert zones to strings for multi_select
        current_zones = options.get(CONF_ZONES, DEFAULT_ZONES)
        if isinstance(current_zones, list):
            zone_defaults = [str(z) for z in current_zones if 1 <= z <= 6]
        else:
            zone_defaults = [str(z) for z in DEFAULT_ZONES]
        
        data_schema = vol.Schema({
            vol.Optional(
                CONF_ZONES,
                default=zone_defaults,
            ): cv.multi_select({str(i): f"Zone {i}" for i in range(1, 7)}),
            vol.Optional(
                CONF_POLL_INTERVAL,
                default=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=3600)),
            vol.Optional(
                CONF_AUTO_POLL,
                default=options.get(CONF_AUTO_POLL, DEFAULT_AUTO_POLL),
            ): bool,
        })

        return self.async_show_form(step_id="init", data_schema=data_schema)

    async def async_step_spotlight(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Spotlight plan settings step: LED indices, max LEDs.
        
        Collects: max LEDs per zone, spotlight plan lights (comma-delimited).
        Normalizes LED indices on submit. Proceeds to verification step.
        """
        if user_input is not None:
            self._options.update(user_input)
            # Normalize spotlight plan lights
            if CONF_SPOTLIGHT_PLAN_LIGHTS in user_input:
                max_leds = user_input.get(CONF_MAX_LEDS, self._options.get(CONF_MAX_LEDS, DEFAULT_MAX_LEDS))
                spotlight_lights_raw = user_input[CONF_SPOTLIGHT_PLAN_LIGHTS]
                if spotlight_lights_raw:
                    self._options[CONF_SPOTLIGHT_PLAN_LIGHTS] = normalize_led_indices(spotlight_lights_raw, max_leds)
                else:
                    self._options[CONF_SPOTLIGHT_PLAN_LIGHTS] = ""
            return await self.async_step_verification()

        options = self._options if self._options else self.config_entry.options
        
        spotlight_lights = options.get(CONF_SPOTLIGHT_PLAN_LIGHTS, DEFAULT_SPOTLIGHT_PLAN_LIGHTS)
        max_leds = options.get(CONF_MAX_LEDS, DEFAULT_MAX_LEDS)
        spotlight_display = self._get_spotlight_plan_lights_display(spotlight_lights, max_leds)
        
        data_schema = vol.Schema({
            vol.Optional(
                CONF_MAX_LEDS,
                default=options.get(CONF_MAX_LEDS, DEFAULT_MAX_LEDS),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
            vol.Optional(
                CONF_SPOTLIGHT_PLAN_LIGHTS,
                default=spotlight_lights,
            ): str,
        })

        return self.async_show_form(
            step_id="spotlight",
            data_schema=data_schema,
            description_placeholders={"current_lights": spotlight_display}
        )

    async def async_step_verification(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Command verification settings step.
        
        Collects: verify commands toggle, retries, delay, timeout.
        Proceeds to advanced step on submit.
        """
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_advanced()

        options = self._options if self._options else self.config_entry.options
        
        data_schema = vol.Schema({
            vol.Optional(
                CONF_VERIFY_COMMANDS,
                default=options.get(CONF_VERIFY_COMMANDS, DEFAULT_VERIFY_COMMANDS),
            ): bool,
            vol.Optional(
                CONF_VERIFICATION_RETRIES,
                default=options.get(CONF_VERIFICATION_RETRIES, DEFAULT_VERIFICATION_RETRIES),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
            vol.Optional(
                CONF_VERIFICATION_DELAY,
                default=options.get(CONF_VERIFICATION_DELAY, DEFAULT_VERIFICATION_DELAY),
            ): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
            vol.Optional(
                CONF_VERIFICATION_TIMEOUT,
                default=options.get(CONF_VERIFICATION_TIMEOUT, DEFAULT_VERIFICATION_TIMEOUT),
            ): vol.All(vol.Coerce(int), vol.Range(min=10, max=120)),
        })

        return self.async_show_form(step_id="verification", data_schema=data_schema)

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Advanced settings step: timeouts, debug logging.
        
        Collects: command timeout, debug logging toggle.
        Saves all options and completes flow on submit.
        """
        if user_input is not None:
            self._options.update(user_input)
            # Save all options
            return self.async_create_entry(title="", data=self._options)

        options = self._options if self._options else self.config_entry.options
        
        data_schema = vol.Schema({
            vol.Optional(
                CONF_COMMAND_TIMEOUT,
                default=options.get(CONF_COMMAND_TIMEOUT, DEFAULT_COMMAND_TIMEOUT),
            ): vol.All(vol.Coerce(int), vol.Range(min=5, max=30)),
            vol.Optional(
                CONF_DEBUG_LOGGING,
                default=options.get(CONF_DEBUG_LOGGING, DEFAULT_DEBUG_LOGGING),
            ): bool,
        })

        return self.async_show_form(step_id="advanced", data_schema=data_schema)
