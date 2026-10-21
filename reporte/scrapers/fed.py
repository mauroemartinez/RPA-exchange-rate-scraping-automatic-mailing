"""Effective Federal Funds Rate (EFFR) de la API FRED, vía httpx asíncrono.

Si FRED falla, la misma tasa sale del New York Fed, que es quien la calcula y la
publica (FRED la toma de ahí). El 21/10/2026 FRED estuvo en mantenimiento y
respondía 200 con una página HTML: sin respaldo, eso frenaba el reporte entero
por un dato que cambia solo cuando decide la FED.
"""

import logging
from datetime import date

import httpx

from reporte.scrapers.utils import ScraperError, cliente_http, retry_http

log = logging.getLogger(__name__)

API_URL = "https://api.stlouisfed.org/fred/series/observations"
SERIE_EFFR = "EFFR"
URL_NY_FED = "https://markets.newyorkfed.org/api/rates/unsecured/effr/last/10.json"

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


def _json(response: httpx.Response, fuente: str):
    response.raise_for_status()
    if "json" not in response.headers.get("content-type", ""):
        raise ValueError(f"{fuente} devolvió una página en vez de datos (¿mantenimiento?)")
    return response.json()


@retry_http
async def _get_observaciones(client: httpx.AsyncClient, api_key: str) -> list[dict]:
    response = await client.get(
        API_URL,
        params={
            "series_id": SERIE_EFFR,
            "api_key": api_key,
            "file_type": "json",
            "sort_order": "desc",
            "limit": 10,  # margen por si los últimos días vienen sin dato
        },
    )
    return _json(response, "FRED")["observations"]


@retry_http
async def _get_ny_fed(client: httpx.AsyncClient) -> list[dict]:
    return _json(await client.get(URL_NY_FED), "New York Fed")["refRates"]


def _ultima_fred(observaciones: list[dict]) -> dict:
    # FRED marca los días sin dato (feriados) con "." en vez de un número.
    for obs in observaciones:
        if obs["value"] != ".":
            return {"fed_tea": float(obs["value"]), "fed_tea_fecha": date.fromisoformat(obs["date"])}
    raise ValueError("las últimas 10 observaciones vinieron todas vacías")


def _ultima_ny_fed(tasas: list[dict]) -> dict:
    con_dato = [t for t in tasas if t.get("type") == "EFFR" and t.get("percentRate") is not None]
    if not con_dato:
        raise ValueError("las últimas 10 publicaciones vinieron sin tasa")
    ultima = max(con_dato, key=lambda t: t["effectiveDate"])
    return {"fed_tea": float(ultima["percentRate"]), "fed_tea_fecha": date.fromisoformat(ultima["effectiveDate"])}


def _sin_url(exc: Exception) -> str:
    # El mensaje de httpx incluye la URL completa, y la de FRED lleva la API key en
    # la query string: llegaba tal cual al mail de alerta y al log. Del error HTTP
    # queda solo el código.
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return f"{type(exc).__name__}: {exc}"


async def run(client: httpx.AsyncClient | None = None, api_key: str | None = None) -> dict:
    """Última EFFR publicada, con su fecha. Claves: fed_tea, fed_tea_fecha."""
    if api_key is None:
        # Import diferido: así importar el paquete scrapers no exige un .env válido.
        from reporte.config import settings

        api_key = settings.fed_api_key.get_secret_value()

    async with cliente_http(client, TIMEOUT) as c:
        try:
            return _ultima_fred(await _get_observaciones(c, api_key))
        except Exception as exc:
            falla_fred = _sin_url(exc)
        log.warning("FRED falló (%s): la EFFR sale del New York Fed", falla_fred)
        try:
            return _ultima_ny_fed(await _get_ny_fed(c))
        except Exception as exc:
            falla_ny_fed = _sin_url(exc)

    # Sin encadenar la excepción original: el traceback de la alerta recorre la
    # cadena de causas, y la de httpx trae la URL con la key.
    causa = RuntimeError(f"FRED: {falla_fred}; New York Fed: {falla_ny_fed}")
    raise ScraperError("FED", "leer EFFR", causa) from None
