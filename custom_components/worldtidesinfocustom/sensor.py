"""Sensor worldtides.info."""
# Python library
import logging
import time
from datetime import datetime, timedelta

# HA library
import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import (
    ATTR_ATTRIBUTION,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_API_KEY,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_NAME,
    CONF_SHOW_ON_MAP,
    LENGTH_FEET,
    LENGTH_KILOMETERS,
    LENGTH_METERS,
    LENGTH_MILES,
)
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.util.distance import convert as dist_convert
from homeassistant.util.unit_system import IMPERIAL_SYSTEM

KM_PER_MI = dist_convert(1, LENGTH_MILES, LENGTH_KILOMETERS)
MI_PER_KM = dist_convert(1, LENGTH_KILOMETERS, LENGTH_MILES)
FT_PER_M = dist_convert(1, LENGTH_METERS, LENGTH_FEET)

_LOGGER = logging.getLogger(__name__)

# Component Library
from . import give_persistent_filename
from .const import (
    ATTRIBUTION,
    CONF_PLOT_BACKGROUND,
    CONF_PLOT_COLOR,
    CONF_STATION_DISTANCE,
    CONF_UNIT,
    CONF_VERTICAL_REF,
    DATA_COORDINATOR,
    DEBUG_FLAG,
    DEFAULT_CONF_UNIT,
    DEFAULT_NAME,
    DEFAULT_PLOT_BACKGROUND,
    DEFAULT_PLOT_COLOR,
    DEFAULT_STATION_DISTANCE,
    DEFAULT_VERTICAL_REF,
    DOMAIN,
    HA_CONF_UNIT,
    HALF_TIDE_SLACK_DURATION,
    IMPERIAL_CONF_UNIT,
    METRIC_CONF_UNIT,
    ROUND_COEFF,
    ROUND_HEIGTH,
    ROUND_STATION_DISTANCE,
    SCAN_INTERVAL_SECONDS,
    WORLD_TIDES_INFO_CUSTOM_DOMAIN,
    WWW_PATH,
)

# import .storage_mngt
from .py_worldtidesinfo import (
    PLOT_CURVE_UNIT_FT,
    PLOT_CURVE_UNIT_M,
    WorldTidesInfo_server,
    give_info_from_raw_data,
    give_info_from_raw_data_N_and_N_1,
    give_info_from_raw_datums_data,
)
from .server_request_scheduler import WorldTidesInfo_server_scheduler
from .storage_mngt import File_Data_Cache, File_Picture

# Sensor HA parameter
SCAN_INTERVAL = timedelta(seconds=SCAN_INTERVAL_SECONDS)

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_API_KEY): cv.string,
        vol.Optional(CONF_LATITUDE): cv.latitude,
        vol.Optional(CONF_LONGITUDE): cv.longitude,
        vol.Optional(CONF_VERTICAL_REF, default=DEFAULT_VERTICAL_REF): cv.string,
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Optional(
            CONF_STATION_DISTANCE,
            default=DEFAULT_STATION_DISTANCE,
        ): cv.positive_int,
        vol.Optional(CONF_PLOT_COLOR, default=DEFAULT_PLOT_COLOR): cv.string,
        vol.Optional(CONF_PLOT_BACKGROUND, default=DEFAULT_PLOT_BACKGROUND): cv.string,
        vol.Optional(CONF_UNIT, default=DEFAULT_CONF_UNIT): cv.string,
    }
)


def setup_sensor(
    hass,
    name,
    lat,
    lon,
    key,
    vertical_ref,
    plot_color,
    plot_background,
    tide_station_distance,
    unit_to_display,
    show_on_map,
):
    """setup sensor with server, server scheduler in async or sync configuration"""

    # prepare filename
    filenames = give_persistent_filename(hass, name)
    # prepare the tide picture management
    tide_picture_file = File_Picture(
        hass.config.path(WWW_PATH), filenames.get("curve_filename")
    )

    tide_cache_file = File_Data_Cache(
        filenames.get("persistent_data_filename"),
        key,
    )

    # unit used for display, and convert tide station distance
    if unit_to_display == IMPERIAL_CONF_UNIT:
        server_tide_station_distance = tide_station_distance * KM_PER_MI
        unit_curve_picture = PLOT_CURVE_UNIT_FT
    else:
        server_tide_station_distance = tide_station_distance
        unit_curve_picture = PLOT_CURVE_UNIT_M

    # instanciate server front end
    worldtidesinfo_server = WorldTidesInfo_server(
        key,
        lat,
        lon,
        vertical_ref,
        server_tide_station_distance,
        plot_color,
        plot_background,
        unit_curve_picture,
    )
    worldtidesinfo_server_parameter = worldtidesinfo_server.give_parameter()

    # instantiate scheduler front end
    worldtidesinfo_server_scheduler = WorldTidesInfo_server_scheduler(
        key,
        worldtidesinfo_server_parameter,
    )

    # create the sensor
    tides = WorldTidesInfoCustomSensor(
        hass,
        name,
        unit_to_display,
        show_on_map,
        tide_picture_file,
        tide_cache_file,
        worldtidesinfo_server,
        worldtidesinfo_server_scheduler,
    )

    return tides


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the WorldTidesInfo Custom sensor."""

    # Get data from configuration.yaml
    name = config.get(CONF_NAME)
    lat = config.get(CONF_LATITUDE, hass.config.latitude)
    lon = config.get(CONF_LONGITUDE, hass.config.longitude)

    if None in (lat, lon):
        _LOGGER.error("Latitude or longitude not set in Home Assistant config")
        return

    key = config.get(CONF_API_KEY)
    vertical_ref = config.get(CONF_VERTICAL_REF)
    plot_color = config.get(CONF_PLOT_COLOR)
    plot_background = config.get(CONF_PLOT_BACKGROUND)
    # worldides_request_interval = config.get(CONF_WORLDTIDES_REQUEST_INTERVAL)
    tide_station_distance = config.get(CONF_STATION_DISTANCE)

    # what is the unit used
    if config.get(CONF_UNIT) == HA_CONF_UNIT and hass.config.units == IMPERIAL_SYSTEM:
        unit_to_display = IMPERIAL_CONF_UNIT
    elif config.get(CONF_UNIT) == IMPERIAL_CONF_UNIT:
        unit_to_display = IMPERIAL_CONF_UNIT
    else:
        unit_to_display = METRIC_CONF_UNIT

    show_on_map = True

    tides = setup_sensor(
        hass,
        name,
        lat,
        lon,
        key,
        vertical_ref,
        plot_color,
        plot_background,
        tide_station_distance,
        unit_to_display,
        show_on_map,
    )

    tides.update()
    if tides._worldtidesinfo_server_scheduler.no_data():
        _LOGGER.error(f"No data available for this location: {name}")
        return

    add_entities([tides])


async def async_setup_entry(hass, config_entry, async_add_entities):
    """Set up WorldTidesInfo sensors based on a config entry."""
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR][config_entry.entry_id]

    config = config_entry.data

    # Get data from config flow
    name = config.get(CONF_NAME)
    lat = config.get(CONF_LATITUDE)
    lon = config.get(CONF_LONGITUDE)

    # shall not occur
    if None in (lat, lon):
        _LOGGER.error("Latitude or longitude not set in Home Assistant config")
        return

    key = config.get(CONF_API_KEY)
    vertical_ref = config.get(CONF_VERTICAL_REF)
    plot_color = config.get(CONF_PLOT_COLOR)
    plot_background = config.get(CONF_PLOT_BACKGROUND)
    tide_station_distance = config.get(CONF_STATION_DISTANCE)

    # what is the unit used
    if config.get(CONF_UNIT) == HA_CONF_UNIT and hass.config.units == IMPERIAL_SYSTEM:
        unit_to_display = IMPERIAL_CONF_UNIT
    elif config.get(CONF_UNIT) == IMPERIAL_CONF_UNIT:
        unit_to_display = IMPERIAL_CONF_UNIT
    else:
        unit_to_display = METRIC_CONF_UNIT

    if config_entry.options[CONF_SHOW_ON_MAP]:
        show_on_map = True
    else:
        show_on_map = False

    tides = setup_sensor(
        hass,
        name,
        lat,
        lon,
        key,
        vertical_ref,
        plot_color,
        plot_background,
        tide_station_distance,
        unit_to_display,
        show_on_map,
    )

    _LOGGER.debug(f"Launch fetching data available for this location: {name}")
    await tides.async_update()

    if tides._worldtidesinfo_server_scheduler.no_data():
        _LOGGER.error(f"No data available for this location: {name}")
        return

    async_add_entities([tides], True)


class WorldTidesInfoCustomSensor(Entity):
    """Representation of a WorldTidesInfo sensor."""

    def __init__(
        self,
        hass,
        name,
        unit_to_display,
        show_on_map,
        tide_picture_file,
        tide_cache_file,
        worldtidesinfo_server,
        worldtidesinfo_server_scheduler,
    ):
        """Initialize the sensor."""

        self._hass = hass
        # Parameters from configuration.yaml
        self._name = name
        self._unit_to_display = unit_to_display
        self._show_on_map = show_on_map

        # Picture data
        self._tide_picture_file = tide_picture_file

        # World Tide Info Server
        self._worldtidesinfo_server = worldtidesinfo_server
        # the scheduler
        self._worldtidesinfo_server_scheduler = worldtidesinfo_server_scheduler
        # set first trigger of scheduler
        self._worldtidesinfo_server_scheduler.setup_next_midnights()
        # Initialize the data to store
        self._tide_cache_file = tide_cache_file

        self.credit_used = 0

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def device_state_attributes(self):
        """Return the state attributes of this device."""
        attr = {ATTR_ATTRIBUTION: ATTRIBUTION}

        current_time = time.time()

        if self._unit_to_display == IMPERIAL_CONF_UNIT:
            convert_meter_to_feet = FT_PER_M
            convert_km_to_miles = MI_PER_KM
        else:
            convert_meter_to_feet = 1
            convert_km_to_miles = 1

        # Unit system
        attr["Unit displayed"] = self._unit_to_display

        if self._worldtidesinfo_server_scheduler.no_data():
            return attr

        # retrieve tide data
        data = self._worldtidesinfo_server_scheduler._Data_Retrieve.data
        # retrieve previous tide data in case
        previous_data = (
            self._worldtidesinfo_server_scheduler._Data_Retrieve.previous_data
        )
        # the decoder
        tide_info = give_info_from_raw_data_N_and_N_1(data, previous_data)

        # retrieve init data
        init_data = self._worldtidesinfo_server_scheduler._Data_Retrieve.init_data
        init_tide_info = give_info_from_raw_data(init_data)
        # retrieve the datum
        data_datums_offset = (
            self._worldtidesinfo_server_scheduler._Data_Retrieve.data_datums_offset
        )
        datums_info = give_info_from_raw_datums_data(data_datums_offset)

        # compute the Mean Water Spring offset
        MWS_datum_offset = datums_info.give_mean_water_spring_datums_offset()

        # The vertical reference used : LAT, ...
        vertical_ref = tide_info.give_vertical_ref()
        if vertical_ref.get("error") == None:
            attr["vertical_reference"] = vertical_ref.get("vertical_ref")
        else:
            attr["vertical_reference"] = "No vertical ref"

        # Tide station characteristics
        tide_station_used = tide_info.give_tidal_station_used()
        if tide_station_used.get("error") == None:
            attr["tidal_station_used"] = tide_station_used.get("station")
        else:
            attr["tidal_station_used"] = "No Tide station used"

        # Next tide
        next_tide_UTC = tide_info.give_next_high_low_tide_in_UTC(current_time)
        if next_tide_UTC.get("error") == None:
            attr["high_tide_time_utc"] = next_tide_UTC.get("high_tide_time_utc")
            attr["high_tide_height"] = round(
                next_tide_UTC.get("high_tide_height") * convert_meter_to_feet,
                ROUND_HEIGTH,
            )
            attr["low_tide_time_utc"] = next_tide_UTC.get("low_tide_time_utc")
            attr["low_tide_height"] = round(
                next_tide_UTC.get("low_tide_height") * convert_meter_to_feet,
                ROUND_HEIGTH,
            )

        # Tide Tendancy and time_to_next_tide
        next_tide_in_epoch = tide_info.give_next_tide_in_epoch(current_time)
        previous_tide_in_epoch = tide_info.give_previous_tide_in_epoch(current_time)

        # initialize data for delta time
        delta_current_time_to_next = 0
        delta_current_time_from_previous = 0

        # compute delta tide to next tide
        if next_tide_in_epoch.get("error") == None:
            delta_current_time_to_next = (
                next_tide_in_epoch.get("tide_time") - current_time
            )

        # compute delta time from previous tide
        if previous_tide_in_epoch.get("error") == None:
            delta_current_time_from_previous = (
                current_time - previous_tide_in_epoch.get("tide_time")
            )

        attr["time_to_next_tide"] = "(hours) {}".format(
            timedelta(seconds=delta_current_time_to_next)
        )

        # KEEP FOR DEBUG:
        if DEBUG_FLAG:
            attr["time_from_previous_tide"] = "(hours) {}".format(
                timedelta(seconds=delta_current_time_from_previous)
            )

        # compute tide tendancy
        tide_tendancy = ""
        if next_tide_in_epoch.get("tide_type") == "High":
            if delta_current_time_to_next < HALF_TIDE_SLACK_DURATION:
                tide_tendancy = "Tides Slack (Up)"
            elif previous_tide_in_epoch.get("error") != None:
                # if the previous tide is not found, assume that
                # we are not in slack
                tide_tendancy = "Tides Up"
            elif delta_current_time_from_previous < HALF_TIDE_SLACK_DURATION:
                tide_tendancy = "Tides Slack (Up)"
            else:
                tide_tendancy = "Tides Up"
        else:
            if delta_current_time_to_next < HALF_TIDE_SLACK_DURATION:
                tide_tendancy = "Tides Slack (Down)"
            elif previous_tide_in_epoch.get("error") != None:
                # if the previous tide is not found, assume that
                # we are not in slack
                tide_tendancy = "Tides Down"
            elif delta_current_time_from_previous < HALF_TIDE_SLACK_DURATION:
                tide_tendancy = "Tides Slack (Down)"
            else:
                tide_tendancy = "Tides Down"
        attr["tide_tendancy"] = f"{tide_tendancy}"

        # Display the next amplitude
        diff_next_high_tide_low_tide = 0
        if next_tide_UTC.get("error") == None:
            diff_next_high_tide_low_tide = abs(
                next_tide_UTC.get("high_tide_height")
                - next_tide_UTC.get("low_tide_height")
            )
        attr["next_tide_amplitude"] = round(diff_next_high_tide_low_tide, ROUND_HEIGTH)

        # The next coeff tide_highlow_over the Mean Water Spring
        if MWS_datum_offset.get("error") == None:
            attr["next_Coeff_resp_MWS"] = round(
                (
                    diff_next_high_tide_low_tide
                    / (
                        MWS_datum_offset.get("datum_offset_MHWS")
                        - MWS_datum_offset.get("datum_offset_MLWS")
                    )
                )
                * 100,
                ROUND_COEFF,
            )

        # The height
        current_height_value = tide_info.give_current_height_in_UTC(current_time)
        if current_height_value.get("error") == None:
            attr["current_height_utc"] = current_height_value.get("current_height_utc")
            attr["current_height"] = round(
                current_height_value.get("current_height") * convert_meter_to_feet,
                ROUND_HEIGTH,
            )

        # Display the current amplitude
        current_tide_UTC = tide_info.give_current_high_low_tide_in_UTC(current_time)
        diff_current_high_tide_low_tide = 0
        if current_tide_UTC.get("error") == None:
            diff_current_high_tide_low_tide = abs(
                current_tide_UTC.get("high_tide_height")
                - current_tide_UTC.get("low_tide_height")
            )
        else:
            _LOGGER.debug(
                "No previous data for {}:  {}".format(
                    self._name,
                    current_tide_UTC.get("error"),
                )
            )

        attr["tide_amplitude"] = round(diff_current_high_tide_low_tide, ROUND_HEIGTH)

        # The coeff tide_highlow_over the Mean Water Spring
        if MWS_datum_offset.get("error") == None:
            attr["Coeff_resp_MWS"] = round(
                (
                    diff_current_high_tide_low_tide
                    / (
                        MWS_datum_offset.get("datum_offset_MHWS")
                        - MWS_datum_offset.get("datum_offset_MLWS")
                    )
                )
                * 100,
                ROUND_COEFF,
            )

        # The credit used to display the update
        attr["CreditCallUsed"] = self.credit_used

        # Time where are trigerred the request
        attr["Data_request_time"] = time.strftime(
            "%H:%M:%S %d/%m/%y",
            time.localtime(
                self._worldtidesinfo_server_scheduler._Data_Retrieve.data_request_time
            ),
        )
        # KEEP FOR DEBUG:
        if DEBUG_FLAG:
            attr["Init_data_request_time"] = time.strftime(
                "%H:%M:%S %d/%m/%y",
                time.localtime(
                    self._worldtidesinfo_server_scheduler._Data_Retrieve.init_data_request_time
                ),
            )
            attr[
                "next day midnight"
            ] = self._worldtidesinfo_server_scheduler._Data_Scheduling.next_day_midnight.strftime(
                "%H:%M:%S %d/%m/%y"
            )
            attr[
                "next month midnight"
            ] = self._worldtidesinfo_server_scheduler._Data_Scheduling.next_month_midnight.strftime(
                "%H:%M:%S %d/%m/%y"
            )

        # Filename of tide picture
        attr["plot"] = self._tide_picture_file.full_filename()

        # Tide detailed characteristic
        attr["station_distance"] = round(
            (self._worldtidesinfo_server.give_parameter()).get_tide_station_distance()
            * convert_km_to_miles,
            ROUND_STATION_DISTANCE,
        )
        station_around = init_tide_info.give_station_around_info()
        if station_around.get("error") == None:
            attr["station_around_nb"] = station_around.get("station_around_nb")
            attr["station_around_name"] = station_around.get("station_around_name")
        else:
            attr["station_around_nb"] = 0
            attr["station_around_name"] = "No Station"

        time_zone = init_tide_info.give_nearest_station_time_zone()
        if time_zone.get("error") == None:
            attr["station_around_time_zone"] = time_zone.get("time_zone")
        else:
            attr["station_around_time_zone"] = "No station time zone"

        # Displaying the geography on the map relies upon putting the latitude/longitude
        # in the entity attributes with "latitude" and "longitude" as the keys.
        if self._show_on_map:
            attr[ATTR_LATITUDE] = (
                self._worldtidesinfo_server.give_parameter()
            ).get_latitude()
            attr[ATTR_LONGITUDE] = (
                self._worldtidesinfo_server.give_parameter()
            ).get_longitude()

        return attr

    @property
    def icon(self):
        """return icon tendancy"""
        current_time = time.time()

        # retrieve tide data
        data = self._worldtidesinfo_server_scheduler._Data_Retrieve.data
        # retrieve previous tide data in case of error
        previous_data = (
            self._worldtidesinfo_server_scheduler._Data_Retrieve.previous_data
        )
        # the decoder
        tide_info = give_info_from_raw_data_N_and_N_1(data, previous_data)

        # Tide Tendancy and time_to_next_tide
        next_tide_in_epoch = tide_info.give_next_tide_in_epoch(current_time)
        previous_tide_in_epoch = tide_info.give_previous_tide_in_epoch(current_time)

        # delta time to next tide and from previous tide are set to zero
        delta_current_time_to_next = 0
        delta_current_time_from_previous = 0

        # delta time to next tide
        if next_tide_in_epoch.get("error") == None:
            delta_current_time_to_next = (
                next_tide_in_epoch.get("tide_time") - current_time
            )

        # delta time from previous tide
        if previous_tide_in_epoch.get("error") == None:
            delta_current_time_from_previous = (
                current_time - previous_tide_in_epoch.get("tide_time")
            )

        # compute tide tendancy
        tide_tendancy = "mdi:shore"
        if next_tide_in_epoch.get("tide_type") == "High":
            if delta_current_time_to_next < HALF_TIDE_SLACK_DURATION:
                tide_tendancy = "mdi:chevron-up"
            elif previous_tide_in_epoch.get("error") != None:
                # if delta time from previous tide cannot be computed, assume that
                # we are not in slack
                tide_tendancy = "mdi:chevron-triple-up"
            elif delta_current_time_from_previous < HALF_TIDE_SLACK_DURATION:
                tide_tendancy = "mdi:chevron-up"
            else:
                tide_tendancy = "mdi:chevron-triple-up"
        else:
            if delta_current_time_to_next < HALF_TIDE_SLACK_DURATION:
                tide_tendancy = "mdi:chevron-down"
            elif previous_tide_in_epoch.get("error") != None:
                tide_tendancy = "mdi:chevron-triple-down"
            elif delta_current_time_from_previous < HALF_TIDE_SLACK_DURATION:
                tide_tendancy = "mdi:chevron-down"
            else:
                tide_tendancy = "mdi:chevron-triple-down"
        return tide_tendancy

    @property
    def state(self):
        """Return the state of the device."""
        data = self._worldtidesinfo_server_scheduler._Data_Retrieve.data
        if data:
            tide_info = give_info_from_raw_data(data)
            # Get next tide time
            next_tide = tide_info.give_next_tide_in_epoch(time.time())
            if next_tide.get("error") == None:
                tidetime = time.strftime(
                    "%H:%M", time.localtime(next_tide.get("tide_time"))
                )
                tidetype = next_tide.get("tide_type")
                tide_string = f"{tidetype} tide at {tidetime}"
                return tide_string
        return None

    async def async_update(self):
        """Fetch new state data for this sensor."""
        _LOGGER.debug("Async Update Tides sensor %s", self._name)
        ##Watch Out : only method name is given to function i.e. without ()
        await self._hass.async_add_executor_job(self.update)

    def update(self):
        """Update of sensors."""
        _LOGGER.debug("Sync Update Tides sensor %s", self._name)
        init_data_fetched = False

        self.credit_used = 0
        current_time = time.time()

        # Init data (initialisation or refresh or retrieve from a file)
        if self._worldtidesinfo_server_scheduler.init_data_to_be_fetched(current_time):
            if self._tide_cache_file.Fetch_Stored_Data():
                SchedulerSnapshot = self._tide_cache_file.Data_Read()
                _LOGGER.debug("Snpashot retrieved data file at: %s ", int(current_time))
                if self._worldtidesinfo_server_scheduler.scheduler_snapshot_usable(
                    SchedulerSnapshot
                ):
                    _LOGGER.debug(
                        "Snpashot decoding data file at: %s ", int(current_time)
                    )
                    self._worldtidesinfo_server_scheduler.use_scheduler_image_if_possible(
                        SchedulerSnapshot
                    )
                else:
                    _LOGGER.debug(
                        "Error in decoding data file at: %s", int(current_time)
                    )

        # the data read is empty (the snapshot retrieve is not useable) or too old
        if (
            self._worldtidesinfo_server_scheduler.init_data_to_be_fetched(current_time)
            == True
        ):
            # Retrieve station from server
            self.retrieve_tide_station()
            self._worldtidesinfo_server_scheduler.setup_next_init_data_midnight()
            init_data_fetched = True

        # Update: normal process
        if self._worldtidesinfo_server_scheduler.data_to_be_fetched(
            init_data_fetched, current_time
        ):
            self.retrieve_height_station(init_data_fetched)
            self._worldtidesinfo_server_scheduler.setup_next_data_midnight()
            self._tide_cache_file.store_data(
                self._worldtidesinfo_server_scheduler.give_scheduler_image()
            )
        else:
            _LOGGER.debug(
                "Tide data not need to be requeried at: %s", int(current_time)
            )

    def retrieve_tide_station(self):
        """TIDE STATION : Get the latest data from WorldTidesInfo."""
        if self._worldtidesinfo_server.retrieve_tide_station():
            _LOGGER.debug(
                "Init data queried at: %s",
                self._worldtidesinfo_server.retrieve_tide_station_request_time,
            )
            self.credit_used = (
                self.credit_used
                + self._worldtidesinfo_server.retrieve_tide_station_credit()
            )
            self._worldtidesinfo_server_scheduler._Data_Retrieve.init_data = (
                self._worldtidesinfo_server.retrieve_tide_station_raw_data()
            )
            self._worldtidesinfo_server_scheduler._Data_Retrieve.init_data_request_time = (
                self._worldtidesinfo_server.retrieve_tide_station_request_time()
            )
        else:
            _LOGGER.error(
                "Error retrieving data from WorldTidesInfo: %s",
                self._worldtidesinfo_server.retrieve_tide_station_err_value,
            )

    def retrieve_height_station(self, init_data_fetched):
        """HEIGTH : Get the latest data from WorldTidesInfo."""
        data = None
        datum_flag = (
            self._worldtidesinfo_server_scheduler.no_datum()
            or init_data_fetched == True
        )
        if self._worldtidesinfo_server.retrieve_tide_height_over_one_day(datum_flag):
            _LOGGER.debug(
                "Data queried at: %s",
                self._worldtidesinfo_server.retrieve_tide_request_time,
            )
            # update store data
            data = self._worldtidesinfo_server.retrieve_tide_raw_data()
            self._worldtidesinfo_server_scheduler.store_new_data(
                data, self._worldtidesinfo_server.retrieve_tide_request_time()
            )

            self.credit_used = (
                self.credit_used + self._worldtidesinfo_server.retrieve_tide_credit()
            )

            # process information
            tide_info = give_info_from_raw_data(data)
            datum_content = tide_info.give_datum()
            if datum_content.get("error") == None:
                self._worldtidesinfo_server_scheduler._Data_Retrieve.data_datums_offset = datum_content.get(
                    "datums"
                )
            string_picture = tide_info.give_plot_picture_without_header()
            if string_picture.get("error") == None:
                self._tide_picture_file.store_picture_base64(
                    string_picture.get("image")
                )
            else:
                self._tide_picture_file.remove_previous_picturefile()

        else:
            _LOGGER.error(
                "Error retrieving data from WorldTidesInfo: %s",
                self._worldtidesinfo_server.retrieve_tide_err_value,
            )
