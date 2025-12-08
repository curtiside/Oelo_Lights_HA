"""Support for Oelo Lights.

Oelo Lights Home Assistant Integration

This integration provides control for Oelo Lights controllers via HTTP REST API.
Supports multi-zone control, effect capture, storage, and management.

## Protocol

**Base URL:** `http://{IP_ADDRESS}/`

**Endpoints:**
- `GET /getController` - Returns JSON array of zone statuses
- `GET /setPattern?patternType={type}&zones={zone}&...` - Sets pattern/color for zones

**Key Features:**
- Pattern capture from controller (patterns created in Oelo app first)
- Pattern storage (shared across all zones, up to 200 patterns)
- Pattern renaming and management
- Spotlight plan support (handles 40-LED controller limitation)
- Effect list integration (Home Assistant native)

**Pattern Workflow:**
1. Create/set pattern in Oelo app
2. Capture pattern in Home Assistant (stores for reuse)
3. Rename pattern (optional)
4. Apply pattern to any zone

**Storage:**
- Patterns stored per controller (shared across zones)
- Storage location: `{DOMAIN}_patterns_{entry_id}.json`
- Pattern structure includes: id, name, url_params, plan_type, original_colors
"""

from __future__ import annotations
import shutil
import logging
from pathlib import Path
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN
from .services import async_register_services

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Oelo Lights integration."""
    # Register services
    async_register_services(hass)
    
    # Copy Lovelace card to www directory if it doesn't exist
    await _install_lovelace_card(hass)
    
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the Oelo Lights integration from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, ["light"])
    return True

async def _install_lovelace_card(hass: HomeAssistant) -> None:
    """Copy Lovelace card to www directory and register as resource."""
    try:
        # Get paths
        integration_dir = Path(__file__).parent
        card_source = integration_dir / "www" / "oelo-patterns-card-simple.js"
        www_dir = Path(hass.config.path("www"))
        card_dest = www_dir / "oelo-patterns-card-simple.js"
        
        # Create www directory if it doesn't exist
        www_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy card if source exists
        card_installed = False
        if card_source.exists():
            if not card_dest.exists():
                shutil.copy2(card_source, card_dest)
                card_installed = True
                _LOGGER.info("Lovelace card installed to %s", card_dest)
            elif card_source.stat().st_mtime > card_dest.stat().st_mtime:
                shutil.copy2(card_source, card_dest)
                card_installed = True
                _LOGGER.info("Lovelace card updated at %s", card_dest)
        
        # Try to register as Lovelace resource
        if card_installed or card_dest.exists():
            await _register_lovelace_resource(hass)
            
    except Exception as e:
        # Don't fail integration setup if card copy fails
        _LOGGER.warning("Could not install Lovelace card: %s", e)

async def _register_lovelace_resource(hass: HomeAssistant) -> None:
    """Register Lovelace card as a resource."""
    try:
        # Check if Lovelace is available
        if "lovelace" not in hass.config.components:
            _LOGGER.debug("Lovelace not loaded yet, resource will be registered when available")
            return
        
        # Try to get Lovelace resources
        from homeassistant.components.lovelace.resources import ResourceStorage
        
        # Get the default dashboard
        try:
            resources = ResourceStorage(hass)
            resource_url = "/local/oelo-patterns-card-simple.js"
            resource_type = "module"
            
            # Check if resource already exists
            existing_resources = await resources.async_get_info()
            resource_exists = any(
                res.get("url") == resource_url for res in existing_resources
            )
            
            if not resource_exists:
                # Register the resource
                await resources.async_create_item({
                    "type": resource_type,
                    "url": resource_url,
                })
                _LOGGER.info("Lovelace card resource registered automatically")
            else:
                _LOGGER.debug("Lovelace card resource already registered")
        except Exception as e:
            # Resource registration failed, but that's okay - user can add manually
            _LOGGER.debug("Could not auto-register Lovelace resource: %s. User can add manually at Settings → Dashboards → Resources", e)
            _LOGGER.info("To use the Oelo Patterns card, add resource: /local/oelo-patterns-card-simple.js (JavaScript Module)")
            
    except ImportError:
        # Lovelace resources API not available in this HA version
        _LOGGER.info("To use the Oelo Patterns card, add resource: /local/oelo-patterns-card-simple.js (JavaScript Module) at Settings → Dashboards → Resources")
    except Exception as e:
        _LOGGER.debug("Could not register Lovelace resource: %s", e)
        _LOGGER.info("To use the Oelo Patterns card, add resource: /local/oelo-patterns-card-simple.js (JavaScript Module) at Settings → Dashboards → Resources")

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_forward_entry_unload(entry, "light")
