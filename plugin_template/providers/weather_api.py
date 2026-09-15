from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import requests

try:
    from .base import BaseWeatherProvider, ForecastDay, WeatherSnapshot
except ImportError:  # pragma: no cover
    from providers.base import BaseWeatherProvider, ForecastDay, WeatherSnapshot


class WeatherApiWeatherProvider(BaseWeatherProvider):
    name = "weatherapi"

    def fetch_weather(self, latitude: float, longitude: float, location_name: Optional[str] = None) -> WeatherSnapshot:
        if not self.api_key:
            raise RuntimeError("WeatherAPI key is required.")

        params = {
            "key": self.api_key,
            "q": f"{latitude},{longitude}",
            "days": 5,
            "aqi": "no",
            "alerts": "no",
            "lang": "ru",
        }

        response = requests.get("https://api.weatherapi.com/v1/forecast.json", params=params, timeout=15)
        response.raise_for_status()
        payload = response.json()

        location = payload.get("location") or {}
        current = payload.get("current") or {}
        forecast_data = payload.get("forecast") or {}
        daily = forecast_data.get("forecastday") or []

        location_name = location_name or location.get("name") or "Location"
        temperature = self._coerce_float(current.get("temp_c"), 0.0)
        feels_like = self._coerce_float(current.get("feelslike_c"), temperature)
        humidity = self._coerce_int(current.get("humidity"), 0)
        pressure = self._coerce_int(current.get("pressure_mb"), 0)
        wind_speed = self._coerce_float(current.get("wind_kph"), 0.0) / 3.6
        wind_direction = self._coerce_int(current.get("wind_degree"), 0)
        condition = (current.get("condition") or {}).get("text") or "Облачно"
        code = (current.get("condition") or {}).get("code")
        icon = self._weather_code_to_icon(code)

        forecast = []
        for day in daily[:5]:
            day_info = day.get("day") or {}
            condition_info = day_info.get("condition") or {}
            forecast.append(
                ForecastDay(
                    label=datetime.strptime(day.get("date"), "%Y-%m-%d").strftime("%a"),
                    high=self._coerce_float(day_info.get("maxtemp_c"), 0.0),
                    low=self._coerce_float(day_info.get("mintemp_c"), 0.0),
                    description=(condition_info.get("text") or "Облачно"),
                    icon=self._weather_code_to_icon(condition_info.get("code")),
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
            description=condition,
            icon=icon,
            timestamp=datetime.now(timezone.utc),
            forecast=forecast,
        )

    @staticmethod
    def _weather_code_to_icon(code: Optional[int]) -> str:
        if code in (1000,):
            return "d_c1"
        if code in (1003, 1006, 1030):
            return "d_c2"
        if code in (1150, 1153, 1168, 1183, 1186, 1189, 1192, 1195, 1198, 1201, 1204, 1207, 1240, 1243, 1246, 1249, 1252):
            return "d_c3_r3"
        if code in (1063, 1072, 1087, 1150, 1153, 1168, 1183, 1186, 1189, 1192, 1195, 1198, 1201, 1204, 1207, 1240, 1243, 1246, 1249, 1252):
            return "d_c3_r3"
        if code in (1066, 1114, 1117, 1210, 1213, 1216, 1219, 1222, 1225, 1255, 1258, 1261, 1264):
            return "d_c1_s2"
        if code in (1087, 1273, 1276, 1279, 1282):
            return "d_c1_st"
        return "d_c2"
