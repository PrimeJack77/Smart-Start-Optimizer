import logging
from datetime import timedelta

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import DOMAIN, CONF_EPEX_ENTITY, CONF_LOAD_PROFILE

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    """Set up the sensor from a configuration entry (UI)."""
    name = entry.data.get("name")
    epex_entity = entry.data.get(CONF_EPEX_ENTITY)
    
    # Transform the text string into a list of numbers
    profile_str = entry.data.get(CONF_LOAD_PROFILE)
    load_profile = [float(x.strip()) for x in profile_str.split(",")]

    async_add_entities([SmartStartOptimizerSensor(hass, entry.entry_id, name, epex_entity, load_profile)])

class SmartStartOptimizerSensor(SensorEntity):
    def __init__(self, hass, entry_id, name, epex_entity, load_profile):
        self.hass = hass
        self._attr_name = name
        self._attr_unique_id = f"smart_start_{entry_id}" # Allows renaming the entity from the UI
        self._epex_entity = epex_entity
        self._load_profile = load_profile
        self._attr_native_value = None
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_extra_state_attributes = {"min_cost": None}

    async def async_added_to_hass(self):
        """Subscribe to state changes."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self._epex_entity], self._async_epex_changed
            )
        )
        self._calculate_optimal_time()

    async def _async_epex_changed(self, event):
        self._calculate_optimal_time()
        self.async_write_ha_state()

    def _calculate_optimal_time(self):
        """Calculation algorithm."""
        epex_state = self.hass.states.get(self._epex_entity)
        if not epex_state or 'data' not in epex_state.attributes:
            return

        epex_data = epex_state.attributes['data']
        now = dt_util.now()

        prices_15min = {}
        
        for i, entry in enumerate(epex_data):
            start_time = dt_util.parse_datetime(entry.get('start_time'))
            if not start_time or start_time < now.replace(minute=0, second=0, microsecond=0):
                continue
            
            price = entry.get('price_per_kwh')
            
            # Determine the duration of the current time slot
            duration = None
            if entry.get('end_time'):
                # If the EPEX integration provides an end time
                end_time = dt_util.parse_datetime(entry.get('end_time'))
                if end_time:
                    duration = end_time - start_time
                    
            if not duration and (i + 1 < len(epex_data)):
                # Otherwise, calculate the time difference with the next element
                next_start = dt_util.parse_datetime(epex_data[i+1].get('start_time'))
                if next_start:
                    duration = next_start - start_time
                    
            # If neither 'end_time' nor a next element is available, assume 15 minutes by default
            if not duration:
                duration = timedelta(minutes=15) # Note: Fixed typo 'inutes' to 'minutes'

            # Calculate the number of 15-minute blocks in this duration
            # (e.g., 3600 seconds // 900 = 4 blocks for 1h, 900 // 900 = 1 block for 15min)
            slots = int(duration.total_seconds() // 900)
            if slots < 1:
                slots = 1 # Safety fallback
            
            # Assign the price to each 15-minute block
            for j in range(slots):
                interval_time = start_time + timedelta(minutes=15 * j)
                prices_15min[interval_time] = price

        if not prices_15min:
            return

        available_times = sorted(prices_15min.keys())
        profile_length = len(self._load_profile)
        
        min_cost = float('inf')
        best_start_time = None

        for i in range(len(available_times) - profile_length + 1):
            start_time = available_times[i]
            if start_time < now:
                continue

            current_cost = 0
            for j in range(profile_length):
                interval_time = available_times[i + j]
                current_cost += self._load_profile[j] * prices_15min[interval_time]
            
            if current_cost < min_cost:
                min_cost = current_cost
                best_start_time = start_time

        # 3. Update the sensor and create the timestamped attribute
        if best_start_time:
            self._attr_native_value = best_start_time
            
            # Create the timestamped load profile
            scheduled_profile = []
            for j in range(profile_length):
                step_time = best_start_time + timedelta(minutes=15 * j)
                step_consumption = self._load_profile[j]
                step_price = prices_15min.get(step_time, 0)
                step_cost = step_consumption * step_price
                
                scheduled_profile.append({
                    "start_time": step_time.isoformat(),
                    "consumption_kwh": step_consumption,
                    "price": step_price,
                    "cost": round(step_cost, 4)
                })

            self._attr_extra_state_attributes = {
                "min_cost": round(min_cost, 4),
                "scheduled_profile": scheduled_profile
            }