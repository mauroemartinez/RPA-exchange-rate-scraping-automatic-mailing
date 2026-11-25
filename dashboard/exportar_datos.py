"""Exporta los datos del tablero publicado a dashboard/data/, desde el 1 de enero de hace dos años.

- mercado.csv: Fact_Mercado_Macro (dólares, riesgo país, tasas y análisis de IA), sin
  ai_secciones (el JSON interno de la IA).
- series.csv: Fact_Series_Macro (inflación, agregados monetarios, letras del BCRA,
  deuda del Tesoro, mayorista) en formato largo, más el bitcoin de Yahoo Finance.

Solo se publica desde el 1 de enero de hace dos años: el repo es público y la base
completa no se regala. Lee la base dentro de una transacción READ ONLY. Lo corre el
workflow datos-dashboard.yml una vez por día hábil, después de la corrida diaria.

Uso: SUPABASE_DB_URL=... python dashboard/exportar_datos.py
"""

import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

CARPETA = Path(__file__).resolve().parent / "data"


def desde() -> date:
    return date(date.today().year - 2, 1, 1)


def bitcoin(inicio: date) -> pd.DataFrame:
    """Cierre diario de BTC-USD. Si Yahoo falla, se conserva lo que haya en el CSV anterior."""
    try:
        import yfinance as yf

        precios = yf.Ticker("BTC-USD").history(start=inicio.isoformat(), interval="1d", auto_adjust=False)["Close"]
        if precios.empty:
            raise ValueError("sin datos")
    except Exception as exc:  # sin red, sin yfinance o un cambio de Yahoo
        print(f"Bitcoin: no se pudo leer ({exc.__class__.__name__}); se conserva el anterior", file=sys.stderr)
        anterior = CARPETA / "series.csv"
        if anterior.exists():
            viejo = pd.read_csv(anterior)
            return viejo[viejo["serie"] == "bitcoin"]
        return pd.DataFrame(columns=["serie", "Fecha", "valor", "unidad", "fuente"])
    precios.index = pd.to_datetime(precios.index).tz_localize(None).normalize()
    return pd.DataFrame({"serie": "bitcoin", "Fecha": precios.index.date, "valor": precios.round(2).values,
                         "unidad": "USD", "fuente": "Yahoo Finance"})


def main() -> int:
    url = os.environ.get("DASHBOARD_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    if not url:
        print("Falta SUPABASE_DB_URL o DASHBOARD_DB_URL", file=sys.stderr)
        return 1
    inicio = desde()
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 30})
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        mercado = pd.read_sql_query(
            text('SELECT * FROM "Fact_Mercado_Macro" WHERE "Fecha" >= :d ORDER BY "Fecha"'), conn, params={"d": inicio})
        series = pd.read_sql_query(
            text('SELECT serie, "Fecha", valor, unidad, fuente FROM "Fact_Series_Macro" '
                 'WHERE "Fecha" >= :d ORDER BY serie, "Fecha"'), conn, params={"d": inicio})
    engine.dispose()

    mercado = mercado.drop(columns=["ai_secciones"], errors="ignore")
    if len(mercado) < 100:
        print(f"Solo {len(mercado)} filas de mercado: algo anda mal, no se pisa la copia", file=sys.stderr)
        return 1
    series = pd.concat([series, bitcoin(inicio)], ignore_index=True)

    CARPETA.mkdir(parents=True, exist_ok=True)
    mercado.to_csv(CARPETA / "mercado.csv", index=False)
    series.to_csv(CARPETA / "series.csv", index=False)
    print(f"Desde {inicio}: {len(mercado)} ruedas de mercado (último {mercado['Fecha'].max()}), "
          f"{len(series)} valores de {series['serie'].nunique()} series")
    return 0


if __name__ == "__main__":
    sys.exit(main())
