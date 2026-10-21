import json
from datetime import date

import httpx
import pytest

from reporte.scrapers import fed
from reporte.scrapers.utils import ScraperError, run_async

FRED = {"observations": [{"date": "2026-10-20", "value": "."}, {"date": "2026-10-19", "value": "3.88"}]}
NY_FED = {"refRates": [
    {"effectiveDate": "2026-10-20", "type": "EFFR", "percentRate": 3.87},
    {"effectiveDate": "2026-10-19", "type": "EFFR", "percentRate": 3.88},
]}
MANTENIMIENTO = httpx.Response(200, text="<!doctype html><title>Site Maintenance</title>",
                               headers={"content-type": "text/html; charset=utf-8"})


def _cliente(fred_responde, ny_fed_responde):
    def responder(request):
        return fred_responde() if request.url.host == "api.stlouisfed.org" else ny_fed_responde()
    return httpx.AsyncClient(transport=httpx.MockTransport(responder))


def _json(datos):
    return lambda: httpx.Response(200, content=json.dumps(datos), headers={"content-type": "application/json"})


def test_fred_saltea_los_dias_sin_dato():
    cliente = _cliente(_json(FRED), lambda: pytest.fail("con FRED andando no se consulta al New York Fed"))
    assert run_async(fed.run(cliente, api_key="k")) == {"fed_tea": 3.88, "fed_tea_fecha": date(2026, 10, 19)}


@pytest.mark.parametrize("falla", [lambda: MANTENIMIENTO, lambda: httpx.Response(404)])
def test_si_fred_falla_la_tasa_sale_del_new_york_fed(falla):
    # 21/10/2026: FRED en mantenimiento respondía 200 con una página HTML
    resultado = run_async(fed.run(_cliente(falla, _json(NY_FED)), api_key="k"))
    assert resultado == {"fed_tea": 3.87, "fed_tea_fecha": date(2026, 10, 20)}


def test_si_fallan_las_dos_el_error_nombra_ambas():
    with pytest.raises(ScraperError) as error:
        run_async(fed.run(_cliente(lambda: MANTENIMIENTO, lambda: httpx.Response(404)), api_key="k"))
    assert "mantenimiento" in str(error.value) and "New York Fed: HTTP 404" in str(error.value)
