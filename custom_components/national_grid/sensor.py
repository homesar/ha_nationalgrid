"""Sensor platform for national_grid."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory

from .const import _LOGGER, DOMAIN, UNIT_CCF, UNIT_KWH, therms_to_ccf
from .entity import NationalGridEntity

PARALLEL_UPDATES = 1

if TYPE_CHECKING:
    from collections.abc import Callable
    from datetime import datetime

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .coordinator import MeterData, NationalGridDataUpdateCoordinator
    from .data import NationalGridConfigEntry


@dataclass(frozen=True, kw_only=True)
class NationalGridSensorEntityDescription(SensorEntityDescription):
    """Describe National Grid sensor entity."""

    value_fn: Callable[[NationalGridDataUpdateCoordinator, MeterData], Any]
    unit_fn: Callable[[MeterData], str | None] | None = None
    device_class_fn: Callable[[MeterData], SensorDeviceClass | None] | None = None
    available_fn: Callable[[MeterData], bool] = lambda _: True


def _get_energy_usage(
    coordinator: NationalGridDataUpdateCoordinator, meter_data: MeterData
) -> float | None:
    """Get the latest energy usage for a meter."""
    fuel_type = meter_data.meter.get("fuelType")
    usage = coordinator.get_latest_usage(meter_data.account_id, fuel_type)
    _LOGGER.debug(
        "Getting usage for account=%s, fuel_type=%s: %s",
        meter_data.account_id,
        fuel_type,
        usage,
    )
    if usage:
        value = usage.get("usage")
        if value is not None and fuel_type and fuel_type.upper() == "GAS":
            return therms_to_ccf(value)
        return value
    return None


def _get_energy_cost(
    coordinator: NationalGridDataUpdateCoordinator, meter_data: MeterData
) -> float | None:
    """Get the latest energy cost for a meter."""
    fuel_type = meter_data.meter.get("fuelType")
    cost = coordinator.get_latest_cost(meter_data.account_id, fuel_type)
    if cost:
        return cost.get("amount")
    return None


def _get_energy_unit(meter_data: MeterData) -> str:
    """Get the appropriate energy unit based on fuel type."""
    fuel_type = meter_data.meter.get("fuelType", "").upper()
    if fuel_type == "GAS":
        return UNIT_CCF
    return UNIT_KWH


def _get_energy_device_class(meter_data: MeterData) -> SensorDeviceClass | None:
    """Get the device class based on fuel type."""
    fuel_type = meter_data.meter.get("fuelType", "").upper()
    if fuel_type == "GAS":
        return SensorDeviceClass.GAS
    return SensorDeviceClass.ENERGY


def _get_latest_ami_usage(
    coordinator: NationalGridDataUpdateCoordinator, meter_data: MeterData
) -> float | None:
    """Get the most recent AMI daily usage for a meter."""
    sp = str(meter_data.meter.get("servicePointNumber", ""))
    reading = coordinator.get_latest_ami_usage(sp)
    if reading is None:
        return None
    quantity = reading.get("quantity")
    if quantity is None:
        return None
    fuel_type = meter_data.meter.get("fuelType", "")
    if fuel_type and fuel_type.upper() == "GAS":
        return therms_to_ccf(float(quantity))
    return float(quantity)


def _get_latest_interval_read(
    coordinator: NationalGridDataUpdateCoordinator, meter_data: MeterData
) -> float | None:
    """Get the most recent 15-minute interval read value for a meter."""
    sp = str(meter_data.meter.get("servicePointNumber", ""))
    read = coordinator.get_latest_interval_read(sp)
    if read is None:
        return None
    value = read.get("value")
    return float(value) if value is not None else None


def _get_latest_interval_read_time(
    coordinator: NationalGridDataUpdateCoordinator, meter_data: MeterData
) -> datetime | None:
    """Get the start timestamp of the most recent 15-minute interval read."""
    from datetime import UTC, datetime as dt

    sp = str(meter_data.meter.get("servicePointNumber", ""))
    read = coordinator.get_latest_interval_read(sp)
    if read is None:
        return None
    start_str = read.get("startTime", "")
    if not start_str:
        return None
    try:
        parsed = dt.fromisoformat(start_str)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _get_today_interval_total(
    coordinator: NationalGridDataUpdateCoordinator, meter_data: MeterData
) -> float | None:
    """Get today's total kWh from interval reads."""
    sp = str(meter_data.meter.get("servicePointNumber", ""))
    return coordinator.get_today_interval_total(sp)


def _get_fuel_type(
    _coordinator: NationalGridDataUpdateCoordinator, meter_data: MeterData
) -> str | None:
    """Get the fuel type for a meter."""
    return meter_data.meter.get("fuelType")


SENSOR_DESCRIPTIONS: tuple[NationalGridSensorEntityDescription, ...] = (
    NationalGridSensorEntityDescription(
        key="energy_cost",
        translation_key="energy_cost",
        name="Last Billing Cost",
        native_unit_of_measurement="$",
        device_class=SensorDeviceClass.MONETARY,
        value_fn=_get_energy_cost,
    ),
    NationalGridSensorEntityDescription(
        key="energy_usage",
        translation_key="energy_usage",
        name="Last Billing Usage",
        value_fn=_get_energy_usage,
        unit_fn=_get_energy_unit,
        device_class_fn=_get_energy_device_class,
    ),
    NationalGridSensorEntityDescription(
        key="ami_daily_usage",
        translation_key="ami_daily_usage",
        name="Latest Smart Meter Daily Usage",
        value_fn=_get_latest_ami_usage,
        unit_fn=_get_energy_unit,
        device_class_fn=_get_energy_device_class,
        state_class=SensorStateClass.MEASUREMENT,
        available_fn=lambda md: bool(md.meter.get("hasAmiSmartMeter")),
    ),
    NationalGridSensorEntityDescription(
        key="interval_read",
        translation_key="interval_read",
        name="Latest 15-min Usage",
        native_unit_of_measurement=UNIT_KWH,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_latest_interval_read,
        available_fn=lambda md: bool(md.meter.get("hasAmiSmartMeter"))
        and md.meter.get("fuelType", "").upper() != "GAS",
    ),
    NationalGridSensorEntityDescription(
        key="interval_read_time",
        translation_key="interval_read_time",
        name="Latest 15-min Read Time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_get_latest_interval_read_time,
        available_fn=lambda md: bool(md.meter.get("hasAmiSmartMeter"))
        and md.meter.get("fuelType", "").upper() != "GAS",
    ),
    NationalGridSensorEntityDescription(
        key="interval_today_total",
        translation_key="interval_today_total",
        name="Today's Usage",
        native_unit_of_measurement=UNIT_KWH,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_get_today_interval_total,
        available_fn=lambda md: bool(md.meter.get("hasAmiSmartMeter"))
        and md.meter.get("fuelType", "").upper() != "GAS",
    ),
    NationalGridSensorEntityDescription(
        key="fuel_type",
        translation_key="fuel_type",
        name="Fuel Type",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_get_fuel_type,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,  # noqa: ARG001
    entry: NationalGridConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    coordinator = entry.runtime_data

    entities: list[NationalGridSensor] = []

    # Create sensors for each meter.
    if coordinator.data:
        for service_point_number, meter_data in coordinator.data.meters.items():
            entities.extend(
                NationalGridSensor(
                    coordinator=coordinator,
                    service_point_number=service_point_number,
                    entity_description=description,
                    meter_data=meter_data,
                )
                for description in SENSOR_DESCRIPTIONS
                if description.available_fn(meter_data)
            )

    async_add_entities(entities)


class NationalGridSensor(NationalGridEntity, SensorEntity):
    """National Grid sensor entity."""

    entity_description: NationalGridSensorEntityDescription

    def __init__(
        self,
        coordinator: NationalGridDataUpdateCoordinator,
        service_point_number: str,
        entity_description: NationalGridSensorEntityDescription,
        meter_data: MeterData,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, service_point_number)
        self.entity_description = entity_description
        self._attr_unique_id = (
            f"{DOMAIN}_{service_point_number}_{entity_description.key}"
        )
        # Set dynamic unit based on meter type.
        if entity_description.unit_fn:
            self._attr_native_unit_of_measurement = entity_description.unit_fn(
                meter_data
            )
        # Set dynamic device class based on meter type.
        if entity_description.device_class_fn:
            self._attr_device_class = entity_description.device_class_fn(meter_data)

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        meter_data = self.coordinator.get_meter_data(self._service_point_number)
        if meter_data is None:
            return None
        return self.entity_description.value_fn(self.coordinator, meter_data)
