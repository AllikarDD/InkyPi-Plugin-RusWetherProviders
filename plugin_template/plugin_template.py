from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests
from PIL import Image, ImageDraw
from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import get_font

logger = logging.getLogger(__name__)


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
    """Common contract for weather providers.

    New providers only need to implement fetch_weather() and normalize the response
    into WeatherSnapshot. The rendering layer then stays provider-agnostic.
    """

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


class GismeteoWeatherProvider(BaseWeatherProvider):
    name = "gismeteo"

    def fetch_weather(self, latitude: float, longitude: float, location_name: Optional[str] = None) -> WeatherSnapshot:
        headers = {"X-Gismeteo-Token": self.api_key or ""}
        params = {"locale": self.locale}

        if location_name:
            params["name"] = location_name
        else:
            params["coordinates"] = f"{latitude},{longitude}"

        current_response = requests.get(
            "https://api.gismeteo.net/v4/weather/current",
            params=params,
            headers=headers,
            timeout=15,
        )
        current_response.raise_for_status()
        current_payload = current_response.json()

        forecast_response = requests.get(
            "https://api.gismeteo.net/v4/weather/forecast/h3",
            params={**params, "days": 5},
            headers=headers,
            timeout=15,
        )
        forecast_response.raise_for_status()
        forecast_payload = forecast_response.json()

        current = current_payload.get("current") or {}
        location = current_payload.get("location") or {}
        forecast = forecast_payload.get("forecast") or {}

        description = self._pick_value(current, ("description", "description_full", "condition"), default="Облачно")
        if isinstance(description, list):
            description = description[0] if description else "Облачно"
        if isinstance(description, tuple):
            description = description[0] if description else "Облачно"

        icon_code = self._pick_value(current, ("icon_weather", "icon", "weather_icon"), default="d_c1_r1")
        if isinstance(icon_code, list):
            icon_code = icon_code[0] if icon_code else "d_c1_r1"

        timestamp = datetime.now(timezone.utc)
        try:
            timestamp = datetime.fromisoformat(current.get("time", datetime.now(timezone.utc).isoformat())).replace(tzinfo=timezone.utc)
        except (TypeError, ValueError):
            timestamp = datetime.now(timezone.utc)

        forecast_days = self._normalize_forecast(forecast)

        return WeatherSnapshot(
            location=(location.get("name") or location_name or "Город"),
            temperature=self._coerce_float(current.get("temperature_air"), 0.0),
            feels_like=self._coerce_float(current.get("temperature_heat_index", current.get("temperature_air")), 0.0),
            humidity=self._coerce_int(current.get("humidity"), 0),
            pressure=self._coerce_int(current.get("pressure"), 0),
            wind_speed=self._coerce_float(current.get("wind_speed"), 0.0),
            wind_direction=self._coerce_int(current.get("wind_direction"), 0),
            description=str(description),
            icon=self._normalize_icon_code(icon_code),
            timestamp=timestamp,
            forecast=forecast_days,
        )

    def _normalize_forecast(self, forecast_payload: Dict[str, Any]) -> List[ForecastDay]:
        forecast_days: Dict[str, Dict[str, Any]] = {}
        times = forecast_payload.get("time") or []
        temps = forecast_payload.get("temperature_air") or []
        descriptions = forecast_payload.get("description") or []
        icons = forecast_payload.get("icon_weather") or []

        for idx, time_value in enumerate(times):
            try:
                dt = datetime.fromisoformat(time_value)
            except (TypeError, ValueError):
                continue
            key = dt.date().isoformat()
            bucket = forecast_days.setdefault(
                key,
                {"temps": [], "descriptions": [], "icons": []},
            )
            bucket["temps"].append(self._coerce_float(temps[idx] if idx < len(temps) else 0, 0.0))
            if idx < len(descriptions):
                bucket["descriptions"].append(str(descriptions[idx]))
            if idx < len(icons):
                bucket["icons"].append(str(icons[idx]))

        result: List[ForecastDay] = []
        for key in sorted(forecast_days.keys())[:5]:
            values = forecast_days[key]
            temps_values = values["temps"]
            description_values = values["descriptions"]
            icon_values = values["icons"]
            label = datetime.fromisoformat(key).strftime("%a")
            result.append(
                ForecastDay(
                    label=label,
                    high=max(temps_values) if temps_values else 0.0,
                    low=min(temps_values) if temps_values else 0.0,
                    description=(description_values[0] if description_values else "Облачно"),
                    icon=self._normalize_icon_code(icon_values[0] if icon_values else "d_c1_r1"),
                )
            )
        return result

    @staticmethod
    def _pick_value(payload: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
        for key in keys:
            value = payload.get(key)
            if value not in (None, "", [], {}):
                return value
        return default

    @staticmethod
    def _normalize_icon_code(raw_icon: Any) -> str:
        if not raw_icon:
            return "clear"
        icon = str(raw_icon).lower()
        if "storm" in icon or "r5" in icon or "r4" in icon:
            return "storm"
        if "rain" in icon or "r3" in icon or "r2" in icon or "r1" in icon or "m" in icon:
            return "rain"
        if "snow" in icon or "s" in icon:
            return "snow"
        if "fog" in icon or "cloud" in icon or "c" in icon:
            return "cloud"
        if icon.startswith("n") or "n_" in icon:
            return "night"
        return "clear"


class OpenMeteoWeatherProvider(BaseWeatherProvider):
    name = "open-meteo"

    def fetch_weather(self, latitude: float, longitude: float, location_name: Optional[str] = None) -> WeatherSnapshot:
        params = {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,pressure_msl,wind_speed_10m,wind_direction_10m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min",
            "hourly": "weather_code",
            "timezone": "auto",
            "forecast_days": 7,
            "temperature_unit": "celsius",
            "wind_speed_unit": "ms",
            "precipitation_unit": "mm",
        }

        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()

        current = payload.get("current") or {}
        daily = payload.get("daily") or {}
        daily_times = daily.get("time") or []
        daily_high = daily.get("temperature_2m_max") or []
        daily_low = daily.get("temperature_2m_min") or []
        daily_codes = daily.get("weather_code") or []

        if daily_times:
            location_name = location_name or payload.get("timezone") or "Location"
        else:
            location_name = location_name or "Location"

        temperature = self._coerce_float(current.get("temperature_2m"), 0.0)
        feels_like = self._coerce_float(current.get("apparent_temperature", current.get("temperature_2m")), temperature)
        humidity = self._coerce_int(current.get("relative_humidity_2m"), 0)
        pressure = self._coerce_int(current.get("pressure_msl"), 0)
        wind_speed = self._coerce_float(current.get("wind_speed_10m"), 0.0)
        wind_direction = self._coerce_int(current.get("wind_direction_10m"), 0)
        weather_code = self._coerce_int(current.get("weather_code"), 0)
        description = self._weather_code_to_description(weather_code)
        icon = self._weather_code_to_icon(weather_code, current.get("is_day", 1))

        forecast = []
        for idx in range(min(len(daily_times), 5)):
            code = self._coerce_int(daily_codes[idx] if idx < len(daily_codes) else 0, 0)
            forecast.append(
                ForecastDay(
                    label=datetime.fromisoformat(daily_times[idx]).strftime("%a"),
                    high=self._coerce_float(daily_high[idx] if idx < len(daily_high) else 0, 0.0),
                    low=self._coerce_float(daily_low[idx] if idx < len(daily_low) else 0, 0.0),
                    description=self._weather_code_to_description(code),
                    icon=self._weather_code_to_icon(code, 1),
                )
            )

        return WeatherSnapshot(
            location=location_name,
            temperature=temperature,
            feels_like=feels_like,
            humidity=humidity,
            pressure=pressure,
            wind_speed=wind_speed,
            wind_direction=wind_direction,
            description=description,
            icon=icon,
            timestamp=datetime.now(timezone.utc),
            forecast=forecast,
        )

    @staticmethod
    def _weather_code_to_description(code: int) -> str:
        mapping = {
            0: "Ясно",
            1: "Преимущественно ясно",
            2: "Переменная облачность",
            3: "Пасмурно",
            45: "Туман",
            48: "Туман с инеем",
            51: "Морось",
            53: "Морось",
            55: "Морось",
            56: "Ледяная морось",
            57: "Ледяная морось",
            61: "Небольшой дождь",
            63: "Дождь",
            65: "Сильный дождь",
            66: "Ледяной дождь",
            67: "Ледяной дождь",
            71: "Небольшой снег",
            73: "Снег",
            75: "Сильный снег",
            77: "Снежные зерна",
            80: "Ливни",
            81: "Ливни",
            82: "Сильные ливни",
            85: "Снегопад",
            86: "Сильный снегопад",
            95: "Гроза",
            96: "Гроза с градом",
            99: "Гроза с градом",
        }
        return mapping.get(code, "Облачно")

    @staticmethod
    def _weather_code_to_icon(code: int, is_day: int = 1) -> str:
        if code in (0, 1):
            return "clear" if is_day else "night"
        if code in (2, 3):
            return "cloud"
        if code in (45, 48):
            return "cloud"
        if code in (51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82):
            return "rain"
        if code in (71, 73, 75, 77, 85, 86):
            return "snow"
        if code in (95, 96, 99):
            return "storm"
        return "cloud"


class WeatherProviderFactory:
    """Factory that keeps provider selection separate from rendering logic."""

    @staticmethod
    def create(name: str, api_key: Optional[str] = None, locale: str = "ru-RU", units: str = "metric") -> BaseWeatherProvider:
        provider_name = (name or "gismeteo").strip().lower()
        if provider_name in {"gismeteo", "gismetio", "ru-gismeteo"}:
            return GismeteoWeatherProvider(api_key=api_key, locale=locale, units=units)
        if provider_name in {"open-meteo", "openmeteo", "open_meteo"}:
            return OpenMeteoWeatherProvider(api_key=api_key, locale=locale, units=units)
        raise ValueError(f"Unsupported weather provider: {name}")


class Template(BasePlugin):
    """Weather dashboard template intended for Russian weather providers.

    The plugin is structured so future providers can be added with a new class and a
    single entry in WeatherProviderFactory.create().
    """

    def generate_settings_template(self):
        template_params = super().generate_settings_template()
        template_params["weather_provider"] = {
            "required": True,
            "service": "Gismeteo",
            "expected_key": "GISMETEO_API_TOKEN",
        }
        template_params["style_settings"] = True
        return template_params

    def generate_image(self, settings, device_config):
        dimensions = device_config.get_resolution()
        if device_config.get_config("orientation") == "vertical":
            dimensions = dimensions[::-1]

        provider_name = settings.get("weather_provider") or settings.get("provider") or "Gismeteo"
        location_name = settings.get("location") or settings.get("city") or "Москва"
        api_key = settings.get("api_key") or device_config.load_env_key("GISMETEO_API_TOKEN")
        latitude = settings.get("latitude")
        longitude = settings.get("longitude")

        normalized_provider = (provider_name or "Gismeteo").strip().lower()
        if normalized_provider in {"gismeteo", "gismetio", "ru-gismeteo"} and not api_key:
            raise RuntimeError("Gismeteo API token not configured.")

        if latitude is None or longitude is None:
            latitude = 55.7558
            longitude = 37.6176
            logger.info("No coordinates configured, defaulting to Moscow.")

        try:
            latitude = float(latitude)
            longitude = float(longitude)
        except (TypeError, ValueError):
            raise RuntimeError("Latitude and Longitude must be valid numbers.")

        provider = WeatherProviderFactory.create(provider_name, api_key=api_key, locale="ru-RU", units="metric")
        weather = provider.fetch_weather(latitude, longitude, location_name=location_name)

        return self._render_weather_dashboard(dimensions, weather)

    def _render_weather_dashboard(self, dimensions, weather: WeatherSnapshot):
        width, height = dimensions
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)

        font_title = get_font("Jost", max(18, int(width * 0.07)))
        font_temp = get_font("Jost", max(28, int(width * 0.18)))
        font_secondary = get_font("Jost", max(12, int(width * 0.04)))
        font_small = get_font("Jost", max(10, int(width * 0.03)))

        draw.text((10, 10), weather.location, fill="black", font=font_title)
        draw.text((10, 50), f"{int(round(weather.temperature))}°C", fill="black", font=font_temp)

        condition_symbol = {
            "clear": "☀",
            "night": "☾",
            "cloud": "☁",
            "rain": "☂",
            "storm": "⚡",
            "snow": "❄",
        }.get(weather.icon, "☀")
        draw.text((width - 60, 52), condition_symbol, fill="black", font=font_temp)

        draw.text((10, 115), weather.description, fill="black", font=font_secondary)
        draw.text((10, 145), f"Ощущается как {int(round(weather.feels_like))}°C", fill="black", font=font_secondary)

        metrics = [
            ("Влажность", f"{weather.humidity}%"),
            ("Давление", f"{weather.pressure} мм"),
            ("Ветер", f"{weather.wind_speed} м/с"),
        ]
        metric_box = 110
        metric_y = 190
        for index, (label, value) in enumerate(metrics):
            x = 10 + index * (width // 3)
            draw.rounded_rectangle((x, metric_y, x + 90, metric_y + 55), radius=8, fill="black")
            draw.text((x + 12, metric_y + 8), label, fill="white", font=font_small)
            draw.text((x + 12, metric_y + 22), value, fill="white", font=font_secondary)

        forecast_y = 270
        for index, day in enumerate(weather.forecast[:3]):
            x = 10 + index * 110
            draw.rounded_rectangle((x, forecast_y, x + 95, forecast_y + 80), radius=8, outline="black", width=1)
            draw.text((x + 10, forecast_y + 8), day.label, fill="black", font=font_small)
            draw.text((x + 12, forecast_y + 24), self._forecast_icon(day.icon), fill="black", font=font_secondary)
            draw.text((x + 12, forecast_y + 48), f"{int(day.high)}°", fill="black", font=font_small)
            draw.text((x + 12, forecast_y + 60), f"{int(day.low)}°", fill="black", font=font_small)

        updated = weather.timestamp.strftime("%d.%m %H:%M")
        draw.text((10, height - 18), f"Обновлено: {updated}", fill="black", font=font_small)

        return image

    @staticmethod
    def _forecast_icon(icon: str) -> str:
        mapping = {
            "clear": "☀",
            "night": "☾",
            "cloud": "☁",
            "rain": "☂",
            "storm": "⚡",
            "snow": "❄",
        }
        return mapping.get(icon, "☁")
