from typing import Any
import httpx
import logging

from mcp.server.fastmcp import FastMCP

logging.basicConfig(level=logging.INFO)

# Constants - Use a more specific User-Agent
NWS_API_BASE = "https://api.weather.gov"
USER_AGENT = "WeatherMCPServer/1.0 (shiristern24@gmail.com)"


async def make_nws_request(url: str) -> dict[str, Any] | None:
    """Make a request to the NWS API with proper error handling."""
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/geo+json",
    }
    async with httpx.AsyncClient(verify=False) as client:
        try:
            logging.info("Making request to %s", url)
            response = await client.get(url, headers=headers, timeout=30.0, follow_redirects=True)
            logging.info("Response status: %s", response.status_code)
            # Log the response text for debugging
            if response.status_code != 200:
                logging.error("Response text: %s", response.text[:500])
            if response.status_code == 404:
                logging.error("Error: Location not found (404)")
                return None
            elif response.status_code == 500:
                logging.error("Error: Server error (500)")
                return None
            elif response.status_code == 503:
                logging.error("Error: Service unavailable (503)")
                return None

            response.raise_for_status()
            data = response.json()
            logging.info("Response data keys: %s", data.keys() if data else "None")
            return data
        except httpx.HTTPStatusError as e:
            logging.error("HTTP error: %s - %s", e.response.status_code, e.response.text)
            return None
        except httpx.RequestError as e:
            logging.error("Request error: %s", str(e))
            return None
        except Exception as e:  # noqa: BLE001
            logging.error("Unexpected error: %s", str(e))
            return None


def format_alert(feature: dict) -> str:
    """Format an alert feature into a readable string."""
    props = feature["properties"]
    return f"""
Event: {props.get("event", "Unknown")}
Area: {props.get("areaDesc", "Unknown")}
Severity: {props.get("severity", "Unknown")}
Description: {props.get("description", "No description available")}
Instructions: {props.get("instruction", "No specific instructions provided")}
"""


def register_weather_tools(mcp: FastMCP) -> None:
    """Register all weather-related MCP tools on the given FastMCP instance."""

    @mcp.tool(
        name="nws_active_alerts",
        description=(
            "Active official weather alerts for a US state, including warnings, "
            "watches, and advisories issued by NOAA/NWS. "
            "Use this tool when safety-related or emergency weather information "
            "is required."
        ),
    )
    async def get_alerts(state: str) -> str:
        """Get weather alerts for a US state.

        Args:
            state: Two-letter US state code (e.g. CA, NY)
        """
        url = f"{NWS_API_BASE}/alerts/active/area/{state}"
        data = await make_nws_request(url)

        if not data or "features" not in data:
            return "Unable to fetch alerts or no alerts found."

        if not data["features"]:
            return "No active alerts for this state."

        alerts = [format_alert(feature) for feature in data["features"]]
        return "\n---\n".join(alerts)

    @mcp.tool(
        name="nws_precise_forecast",
        description=(
            "High-precision US weather forecast using the official "
            "NOAA/NWS gridpoints API. Use this when accurate, official, "
            "or structured US weather data is required."
        ),
    )
    async def get_forecast(latitude: float, longitude: float) -> str:
        """Get weather forecast for a location.

        Args:
            latitude: Latitude of the location
            longitude: Longitude of the location
        """
        # First get the forecast grid endpoint
        latitude = round(latitude, 4)
        longitude = round(longitude, 4)
        points_url = f"{NWS_API_BASE}/points/{latitude},{longitude}"
        logging.info("Step 1: Getting grid points for  %s, %s", latitude, longitude)
        points_data = await make_nws_request(points_url)

        if not points_data:
            return (
                "Unable to fetch forecast data for this location. This may be because the location "
                "is outside the US, or the NWS API is having issues."
            )

        # Check that required data is present
        if "properties" not in points_data:
            return f"Error: Unexpected response structure. Keys: {points_data.keys()}"

        if "forecast" not in points_data["properties"]:
            return (
                "Error: No forecast URL in response. "
                f"Available keys: {points_data['properties'].keys()}"
            )

        # Get the forecast URL from the points response
        forecast_url = points_data["properties"]["forecast"]
        logging.info("Step 2: Getting forecast from %s", forecast_url)
        forecast_data = await make_nws_request(forecast_url)

        if not forecast_data:
            return "Unable to fetch detailed forecast."

        # Check that periods exist
        if "properties" not in forecast_data or "periods" not in forecast_data["properties"]:
            return f"Error: No forecast periods in response. Keys: {forecast_data.keys()}"

        # Format the periods into a readable forecast
        periods = forecast_data["properties"]["periods"]
        if not periods:
            return "No forecast periods available."

        forecasts = []
        for period in periods[:5]:  # Only show next 5 periods
            forecast = f"""
{period["name"]}:
Temperature: {period["temperature"]}°{period["temperatureUnit"]}
Wind: {period["windSpeed"]} {period["windDirection"]}
Forecast: {period["detailedForecast"]}
"""
            forecasts.append(forecast)

        return "\n---\n".join(forecasts)


