"""Dólar blue de DolarHoy con Playwright; si DolarHoy falla, el informal de Ámbito.

El 16/11/2026 el bloque principal de la página del blue (.cotizacion_value) quedó
vacío, con un "$" sin número, y la corrida se frenó por la única fuente del blue.
Ahora se lee la tabla "Cotizaciones" de la misma página, que sigue publicando la
fila "Dólar Libre" con compra y venta, y si DolarHoy no responde o cambia otra
vez, el blue sale del informal de Ámbito, que lo publica como JSON.
"""

import logging

import httpx
from playwright.async_api import async_playwright

from reporte.scrapers.utils import ScraperError, cliente_http, parse_money, retry_http, retry_scrape

log = logging.getLogger(__name__)

WEB_DOLARHOY = "https://dolarhoy.com/cotizaciondolarblue"
URL_AMBITO_INFORMAL = "https://mercados.ambito.com//dolar/informal/variacion"

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


@retry_scrape
async def _scrape() -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(WEB_DOLARHOY, wait_until="domcontentloaded")

            # La fila del blue en la tabla "Cotizaciones": un link a esta misma página con
            # las celdas .compra y .venta ("1.570,00")
            fila = page.locator(".cotizaciones_more a[href='/cotizaciondolarblue']").first
            await fila.wait_for()
            tcc_blue = parse_money(await fila.locator(".compra").first.inner_text())
            tcv_blue = parse_money(await fila.locator(".venta").first.inner_text())
        finally:
            await browser.close()

    return {"TCC_Blue": tcc_blue, "TCV_Blue": tcv_blue}


@retry_http
async def _ambito_informal(client: httpx.AsyncClient) -> dict:
    """El blue de Ámbito: {"compra": "1580,00", "venta": "1600,00", "fecha": ...}."""
    response = await client.get(URL_AMBITO_INFORMAL)
    response.raise_for_status()
    datos = response.json()
    return {"TCC_Blue": parse_money(datos["compra"]), "TCV_Blue": parse_money(datos["venta"])}


async def run(client: httpx.AsyncClient | None = None) -> dict:
    """Compra y venta del blue. Claves: TCC_Blue, TCV_Blue."""
    try:
        return await _scrape()
    except Exception as exc:
        falla_dolarhoy = f"{type(exc).__name__}: {exc}"
    log.warning("DolarHoy falló (%s): el blue sale del informal de Ámbito", falla_dolarhoy[:200])
    try:
        async with cliente_http(client, TIMEOUT) as c:
            return await _ambito_informal(c)
    except Exception as exc:
        causa = RuntimeError(f"DolarHoy: {falla_dolarhoy}; Ámbito informal: {type(exc).__name__}: {exc}")
        raise ScraperError("DolarHoy", "leer cotización blue", causa) from None
