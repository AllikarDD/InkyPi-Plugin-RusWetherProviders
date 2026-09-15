from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests

try:
    from .base import BaseWeatherProvider, ForecastDay, WeatherSnapshot
except ImportError:  # pragma: no cover
    from providers.base import BaseWeatherProvider, ForecastDay, WeatherSnapshot


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
            bucket = forecast_days.setdefault(key, {"temps": [], "descriptions": [], "icons": []})
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
            return "d_c1"
        icon = str(raw_icon).strip().lower()
        if icon.startswith("d_") or icon.startswith("n_"):
            return icon
        if "storm" in icon or "r5" in icon or "r4" in icon:
            return "d_c1_st"
        if "rain" in icon or "r3" in icon or "r2" in icon or "r1" in icon or "m" in icon:
            return "d_c3_r3"
        if "snow" in icon or "s" in icon:
            return "d_c1_s2"
        if "fog" in icon or "cloud" in icon or "c" in icon:
            return "d_c2"
        if icon.startswith("n") or "n_" in icon:
            return "n_c1"
        return "d_c1"
