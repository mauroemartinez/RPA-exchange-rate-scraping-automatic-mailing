"""Prototipo de dashboard: corre la app sin navegador, desde un CSV (sin base)."""

from pathlib import Path

import pytest

pytest.importorskip("streamlit", reason="el dashboard tiene sus propias dependencias: dashboard/requirements.txt")
from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parent.parent / "dashboard" / "app.py"


def test_el_dashboard_arranca_desde_el_csv(tmp_path, historico, monkeypatch):
    csv = tmp_path / "historico.csv"
    historico.to_csv(csv, index=False)
    monkeypatch.setenv("DASHBOARD_CSV", str(csv))

    app = AppTest.from_file(str(APP), default_timeout=60).run()

    assert not app.exception
    html = " ".join(m.value for m in app.markdown)
    assert "Seguimiento macroeconómico de Argentina" in html
    # Las seis tarjetas del día, cada una con sus variaciones contra una fecha dicha
    for rotulo in ["Dólar blue (venta)", "Dólar MEP", "Oficial BNA (venta)", "Brecha blue vs. oficial",
                   "Riesgo país", "BADLAR (TEA)"]:
        assert rotulo in html
    # La comparación contra el día hábil anterior siempre está (las de 30 días y el año, si hay historia)
    assert "vs. " in html
    assert len(app.tabs) == 8
    # Cada tema tiene su propio filtro, dentro de su pestaña
    assert [m.label for m in app.multiselect] == ["Cotizaciones oficiales", "Cotizaciones paralelas", "Brechas"]


def test_el_dashboard_no_dice_donde_estan_los_datos(tmp_path, historico, monkeypatch):
    csv = tmp_path / "historico.csv"
    historico.to_csv(csv, index=False)
    monkeypatch.setenv("DASHBOARD_CSV", str(csv))

    app = AppTest.from_file(str(APP), default_timeout=60).run()

    texto = " ".join(m.value for m in app.markdown).lower()
    assert "supabase" not in texto
    assert "postgres" not in texto
