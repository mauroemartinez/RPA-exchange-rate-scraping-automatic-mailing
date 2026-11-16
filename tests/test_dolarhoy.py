import json

import httpx
import pytest

from reporte.scrapers import dolarhoy
from reporte.scrapers.utils import ScraperError, run_async

AMBITO = {"compra": "1580,00", "venta": "1600,00", "fecha": "16/11/2026 - 16:10", "variacion": "1,59%"}


def _cliente(responder):
    return httpx.AsyncClient(transport=httpx.MockTransport(responder))


def _json(datos):
    return lambda request: httpx.Response(200, content=json.dumps(datos), headers={"content-type": "application/json"})


def test_con_dolarhoy_andando_no_se_consulta_a_ambito(monkeypatch):
    async def leido():
        return {"TCC_Blue": 1570.0, "TCV_Blue": 1590.0}

    monkeypatch.setattr(dolarhoy, "_scrape", leido)
    cliente = _cliente(lambda request: pytest.fail("con DolarHoy andando no se consulta a Ámbito"))
    assert run_async(dolarhoy.run(cliente)) == {"TCC_Blue": 1570.0, "TCV_Blue": 1590.0}


def test_si_dolarhoy_falla_el_blue_sale_de_ambito(monkeypatch):
    # 16/11/2026: la página del blue quedó con un "$" sin número
    async def roto():
        raise ValueError("could not convert string to float: ''")

    monkeypatch.setattr(dolarhoy, "_scrape", roto)
    assert run_async(dolarhoy.run(_cliente(_json(AMBITO)))) == {"TCC_Blue": 1580.0, "TCV_Blue": 1600.0}


def test_si_fallan_las_dos_el_error_nombra_ambas(monkeypatch):
    async def roto():
        raise ValueError("could not convert string to float: ''")

    monkeypatch.setattr(dolarhoy, "_scrape", roto)
    with pytest.raises(ScraperError) as error:
        run_async(dolarhoy.run(_cliente(lambda request: httpx.Response(404))))
    assert "DolarHoy: ValueError" in str(error.value) and "Ámbito informal" in str(error.value)
