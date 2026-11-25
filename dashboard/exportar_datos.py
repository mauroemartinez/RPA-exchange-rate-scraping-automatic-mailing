"""Exporta Fact_Mercado_Macro a dashboard/data/mercado.csv, la copia que lee el tablero publicado.

Lee la base dentro de una transacción READ ONLY y deja afuera ai_secciones (el JSON
interno de la IA). Lo corre el workflow datos-dashboard.yml una vez por día hábil.
Así el tablero publicado no necesita credenciales ni dice dónde están los datos.

Uso: SUPABASE_DB_URL=... python dashboard/exportar_datos.py
"""

import os
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

DESTINO = Path(__file__).resolve().parent / "data" / "mercado.csv"


def main() -> int:
    url = os.environ.get("DASHBOARD_DB_URL") or os.environ.get("SUPABASE_DB_URL")
    if not url:
        print("Falta SUPABASE_DB_URL o DASHBOARD_DB_URL", file=sys.stderr)
        return 1
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 30})
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        df = pd.read_sql_query(text('SELECT * FROM "Fact_Mercado_Macro" ORDER BY "Fecha"'), conn)
    engine.dispose()
    df = df.drop(columns=["ai_secciones"], errors="ignore")
    if len(df) < 1000:
        print(f"Solo {len(df)} filas: algo anda mal, no se pisa la copia", file=sys.stderr)
        return 1
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(DESTINO, index=False)
    print(f"{len(df)} filas, último dato {df['Fecha'].max()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
