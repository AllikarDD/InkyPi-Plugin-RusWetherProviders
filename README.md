# InkyPi-Plugin-RusWeatherProviders

![Example of InkyPi-Plugin-RusWeatherProviders](./example.png)

*InkyPi-Plugin-RusWeatherProviders* is a plugin for [InkyPi](https://github.com/fatihak/InkyPi) that renders a weather dashboard on an e-paper display using multiple weather providers.

The plugin is designed to support Russian and international weather APIs in a common architecture, so it is easy to add more providers in the future without changing the display logic.

## What it does

- Displays current weather and short-term forecast on the e-ink display
- Supports multiple providers:
  - Gismeteo
  - Open-Meteo
  - WeatherAPI
- Keeps provider-specific logic isolated from rendering
- Allows configuration through InkyPi plugin settings
- Works with latitude/longitude or a city name

## Supported providers

### Gismeteo

Best choice for Russian weather data and local conditions.

Requirements:
- API token from Gismeteo
- Add it to the plugin settings or store it in your InkyPi environment variable

Expected env key:
```bash
GISMETEO_API_TOKEN=your-token
```

### Open-Meteo

Open, no-key weather service suitable for testing and simple deployments.

### WeatherAPI

Third-party weather provider with good forecast coverage.

Requirements:
- WeatherAPI key

Example env key:
```bash
WEATHERAPI_KEY=your-key
```

---

## Requirements

- InkyPi device running the plugin framework
- A supported weather provider API key when required by that provider
- Optional: configured timezone and display orientation in InkyPi

---

## Installation

### Install

Install the plugin using the InkyPi CLI with the plugin ID and repository URL:

```bash
inkypi plugin install plugin_template https://github.com/your-user/InkyPi-Plugin-RusWeatherProviders
```

If you are testing locally or using a custom fork, replace the URL with your repository URL.

### Plugin settings

After installation, open the plugin settings page and configure:

- Weather provider: `Gismeteo`, `Open-Meteo`, or `WeatherAPI`
- Title (optional)
- Location name or latitude/longitude
- API token for providers that require it

---

## Configuration examples

### Gismeteo

- Provider: `Gismeteo`
- Location: `Москва`
- API token: your Gismeteo token

### Open-Meteo

- Provider: `Open-Meteo`
- Coordinates: `55.7558, 37.6176`
- No API key required

### WeatherAPI

- Provider: `WeatherAPI`
- Coordinates: `55.7558, 37.6176`
- API key: your WeatherAPI key

---

## Provider architecture

The plugin is intentionally structured for extensibility:

- `BaseWeatherProvider` defines the common contract
- each provider implements its own fetch/normalize logic
- a factory selects the correct provider by name
- rendering is completely separate from API-specific code

This means new weather services can be added later by creating a new provider class and registering it in the factory.

---

## Example of using environment variables

Add provider secrets to your InkyPi environment file:

```bash
GISMETEO_API_TOKEN=your-gismeteo-token
WEATHERAPI_KEY=your-weatherapi-key
```

The plugin reads the configured provider values from the settings page or the active device environment where available.

---

## Development status

This plugin is under active development and is structured to grow with additional providers.

---

## License

This project is licensed under the MIT License. See the repository license file for details.
