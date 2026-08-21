import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector
from .const import DOMAIN, CONF_EPEX_ENTITY, CONF_LOAD_PROFILE

class SmartStartConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            # Check load curve format (comma-separated)
            try:
                [float(x.strip()) for x in user_input[CONF_LOAD_PROFILE].split(",")]
                return self.async_create_entry(title=user_input["name"], data=user_input)
            except ValueError:
                errors["base"] = "invalid_profile"

        # Create form
        data_schema = vol.Schema({
            vol.Required("name", default="Best Start Time"): str,
            vol.Required(CONF_EPEX_ENTITY): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")
            ),
            vol.Required(CONF_LOAD_PROFILE, default="1,1,1,1"): str,
        })

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )