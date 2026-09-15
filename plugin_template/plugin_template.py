from __future__ import annotations

import logging
import os
from typing import Optional

from PIL import Image, ImageDraw
from plugins.base_plugin.base_plugin import BasePlugin
from utils.app_utils import get_font

try:
    from .providers.base import WeatherSnapshot
    from .providers.gismeteo import GismeteoWeatherProvider
    from .providers.weather_api import WeatherApiWeatherProvider
except ImportError:  # pragma: no cover
    from providers.base import WeatherSnapshot
    from providers.gismeteo import GismeteoWeatherProvider
    from providers.weather_api import WeatherApiWeatherProvider

logger = logging.getLogger(__name__)


class WeatherProviderFactory:
    """Factory that keeps provider selection separate from rendering logic."""

    @staticmethod
    def create(name: str, api_key: Optional[str] = None, locale: str = "ru-RU", units: str = "metric"):
        provider_name = (name or "gismeteo").strip().lower()
        if provider_name in {"gismeteo", "gismetio", "ru-gismeteo"}:
            return GismeteoWeatherProvider(api_key=api_key, locale=locale, units=units)
        if provider_name in {"weatherapi", "weather-api", "weather_api", "weather api"}:
            return WeatherApiWeatherProvider(api_key=api_key, locale=locale, units=units)
        raise ValueError(f"Unsupported weather provider: {name}")


class Template(BasePlugin):
    """Weather dashboard template that works with multiple providers."""

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
        image = Image.new("RGBA", (width, height), (255, 255, 255, 255))
        draw = ImageDraw.Draw(image)

        font_title = get_font("Jost", max(18, int(width * 0.07)))
        font_temp = get_font("Jost", max(28, int(width * 0.18)))
        font_secondary = get_font("Jost", max(12, int(width * 0.04)))
        font_small = get_font("Jost", max(10, int(width * 0.03)))

        draw.text((10, 10), weather.location, fill="black", font=font_title)
        draw.text((10, 50), f"{int(round(weather.temperature))}°C", fill="black", font=font_temp)

        current_icon_path = self._get_icon_path(weather.icon)
        if current_icon_path:
            current_icon = Image.open(current_icon_path).convert("RGBA")
            icon_size = min(width // 5, 72)
            current_icon = current_icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS)
            image.alpha_composite(current_icon, (width - icon_size - 15, 30))
        else:
            condition_symbol = {
                "d_c1": "☀",
                "n_c1": "☾",
                "d_c2": "☁",
                "d_c3_r3": "☂",
                "d_c1_st": "⚡",
                "d_c1_s2": "❄",
            }.get(weather.icon, "☀")
            draw.text((width - 60, 52), condition_symbol, fill="black", font=font_temp)

        draw.text((10, 115), weather.description, fill="black", font=font_secondary)
        draw.text((10, 145), f"Ощущается как {int(round(weather.feels_like))}°C", fill="black", font=font_secondary)

        metrics = [
            ("Влажность", f"{weather.humidity}%"),
            ("Давление", f"{weather.pressure} мм"),
            ("Ветер", f"{weather.wind_speed} м/с"),
        ]
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

            day_icon_path = self._get_icon_path(day.icon)
            if day_icon_path:
                day_icon = Image.open(day_icon_path).convert("RGBA")
                day_icon = day_icon.resize((28, 28), Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS)
                image.alpha_composite(day_icon, (x + 12, forecast_y + 24))
            else:
                draw.text((x + 12, forecast_y + 24), self._forecast_icon(day.icon), fill="black", font=font_secondary)

            draw.text((x + 12, forecast_y + 48), f"{int(day.high)}°", fill="black", font=font_small)
            draw.text((x + 12, forecast_y + 60), f"{int(day.low)}°", fill="black", font=font_small)

        updated = weather.timestamp.strftime("%d.%m %H:%M")
        draw.text((10, height - 18), f"Обновлено: {updated}", fill="black", font=font_small)

        return image.convert("RGB") #TODO Переделать как в weather.py

    def _get_icon_path(self, icon_name: Optional[str]) -> Optional[str]:
        if not icon_name:
            return None

        candidate = str(icon_name).strip().lower()
        if not candidate:
            return None

        file_name = f"{candidate}.png"
        path = os.path.join(self.get_plugin_dir("icons"), file_name)
        if os.path.exists(path):
            return path

        fallback_map = {
            "clear": "d_c1",
            "night": "n_c1",
            "cloud": "d_c2",
            "rain": "d_c3_r3",
            "storm": "d_c1_st",
            "snow": "d_c1_s2",
        }
        fallback_name = fallback_map.get(candidate)
        if fallback_name:
            fallback_path = os.path.join(self.get_plugin_dir("icons"), f"{fallback_name}.png")
            if os.path.exists(fallback_path):
                return fallback_path
        return None

    @staticmethod
    def _forecast_icon(icon: str) -> str:
        mapping = {
            "d_c1": "☀",
            "n_c1": "☾",
            "d_c2": "☁",
            "d_c3_r3": "☂",
            "d_c1_st": "⚡",
            "d_c1_s2": "❄",
        }
        return mapping.get(icon, "☁")
