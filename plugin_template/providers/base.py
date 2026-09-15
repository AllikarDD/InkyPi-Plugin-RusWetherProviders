from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, List, Optional


@dataclass
class ForecastDay:
    label: str
    high: float
    low: float
    description: str
    icon: str


@dataclass
class WeatherSnapshot:
    location: str
    temperature: float
    feels_like: float
    humidity: int
    pressure: int
    wind_speed: float
    wind_direction: int
    description: str
    icon: str
    timestamp: datetime
    forecast: List[ForecastDay] = field(default_factory=list)


class BaseWeatherProvider:
    """Common contract for weather providers."""

    name = "base"

    def __init__(self, api_key: Optional[str] = None, locale: str = "ru-RU", units: str = "metric"):
        self.api_key = api_key
        self.locale = locale
        self.units = units

    def fetch_weather(self, latitude: float, longitude: float, location_name: Optional[str] = None) -> WeatherSnapshot:
        raise NotImplementedError

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
