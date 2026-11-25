"""Tablero publicado: corre la app sin navegador, desde un CSV (sin base)."""

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

pytest.importorskip("streamlit", reason="el dashboard tiene sus propias dependencias: dashboard/requirements.txt")
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parent.parent
APP = RAIZ / "dashboard" / "app.py"
DATOS = RAIZ / "dashboard" / "data"


def _correr(tmp_path, historico, monkeypatch, lang=None):
    csv = tmp_path / "historico.csv"
    historico.to_csv(csv, index=False)
    monkeypatch.setenv("DASHBOARD_CSV", str(csv))
    app = AppTest.from_file(str(APP), default_timeout=60)
    if lang:
        app.query_params["lang"] = lang
    return app.run()


def test_el_dashboard_arranca_desde_el_csv(tmp_path, historico, monkeypatch):
    app = _correr(tmp_path, historico, monkeypatch)

    assert not app.exception
    html = " ".join(m.value for m in app.markdown)
    assert "Seguimiento macroeconómico de Argentina" in html
    # Las tarjetas del día, cada una con sus variaciones contra una fecha dicha
    for rotulo in ["Dólar blue (venta)", "Dólar MEP", "Oficial BNA (venta)", "Brecha blue vs. oficial",
                   "Riesgo país", "BADLAR (TEA)"]:
        assert rotulo in html
    assert "vs. " in html
    # Una sola vista: las tarjetas van en la barra lateral y los doce temas son un selector, no pestañas
    assert len(app.tabs) == 0
    assert "Dólar blue (venta)" in " ".join(m.value for m in app.sidebar.markdown)
    selectores = [[o.content for o in g.proto.options] for g in app.get("button_group")]
    assert ["Oficiales", "Paralelos", "Brechas", "Riesgo país", "Tasas", "Inflación", "Dinero y BCRA", "Deuda",
            "Bitcoin", "Análisis de IA", "Datos", "Fuentes"] in selectores
    # Solo el tema elegido arma su filtro: el primero, el de las cotizaciones oficiales
    assert [m.label for m in app.multiselect] == ["Cotizaciones oficiales"]


def test_la_suba_del_dolar_se_pinta_como_mala(tmp_path, historico, monkeypatch):
    historico = historico.copy()
    historico.loc[historico.index[-1], "TCV_Blue"] = historico["TCV_Blue"].iloc[-2] * 1.10
    app = _correr(tmp_path, historico, monkeypatch)

    html = " ".join(m.value for m in app.markdown)
    tarjeta_blue = html.split("Dólar blue (venta)")[1].split('class="vidrio tarjeta"')[0]
    assert '<span class="baja"><b>▲' in tarjeta_blue  # en rojo: el dólar subió


def test_el_dashboard_tambien_en_ingles(tmp_path, historico, monkeypatch):
    app = _correr(tmp_path, historico, monkeypatch, lang="en")

    assert not app.exception
    html = " ".join(m.value for m in app.markdown)
    assert "Argentina's macroeconomy, day by day" in html
    assert "Blue dollar (sell)" in html
    assert "Seguimiento macroeconómico" not in html


def test_el_dashboard_no_dice_donde_estan_los_datos(tmp_path, historico, monkeypatch):
    app = _correr(tmp_path, historico, monkeypatch)

    texto = " ".join(m.value for m in app.markdown).lower()
    assert "supabase" not in texto
    assert "postgres" not in texto


@pytest.mark.parametrize("archivo", ["mercado.csv", "series.csv"])
def test_los_datos_publicados_empiezan_el_1_de_enero_de_hace_dos_anios(archivo):
    """El repo es público: la base completa no se publica."""
    ruta = DATOS / archivo
    if not ruta.exists():
        pytest.skip(f"no hay {archivo}")
    hoy = date.today()
    limite = date(hoy.year - 2, 1, 1)
    if hoy.month == 1 and hoy.day <= 10:  # en los primeros días del año el workflow todavía no recortó
        limite = date(hoy.year - 3, 1, 1)
    fechas = pd.to_datetime(pd.read_csv(ruta, usecols=["Fecha"])["Fecha"])
    assert fechas.min().date() >= limite
