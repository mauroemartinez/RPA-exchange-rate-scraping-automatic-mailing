"""Corrige los errores del histórico de Fact_Mercado_Macro contra fuentes independientes.

La auditoría de octubre de 2026 encontró, en la carga histórica y en años de scraping:
valores de relleno (el blue, el solidario y el euro repetidos miles de días con su primer
dato real), comas decimales corridas (MEP, divisas, billete y euro por 10, el solidario
hasta por 10^10), fechas con día y mes invertidos, el blue y el solidario sin moverse
durante semanas mientras el mercado se movía, y la tasa de la FED de 2023 mal cargada.

Uso:
    python scripts/depurar_historico.py             # muestra qué cambiaría; no escribe nada
    python scripts/depurar_historico.py --aplicar   # copia la tabla y aplica todo en una transacción

Las referencias: ArgentinaDatos (blue, oficial, mayorista, MEP, tarjeta y riesgo país),
el A3500 y la BADLAR del BCRA, y la EFFR de la FED. Una referencia sola no alcanza para
reemplazar un dato propio (ArgentinaDatos también tiene días mal cargados): las reglas
piden que el error sea evidente, como una potencia de 10 exacta, o que lo confirme una
segunda fuente. Cada cambio queda en respaldos/ (ignorada por git) con su motivo, junto a
la copia completa de la tabla. Se puede volver a correr: si no encuentra nada, no cambia nada.
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TABLA = "Fact_Mercado_Macro"
NUMERICAS = ["TCC_Blue", "TCV_Blue", "TCC_Billete", "TCV_Billete", "TCC_Divisas", "TCV_Divisas", "Solidario",
             "TCV_MEP", "riesgo_pais", "TCC_Euro", "TCV_Euro", "fed_tea", "bcra_tea"]
RESPALDOS = RAIZ / "respaldos"

URL_ARGENTINADATOS = "https://api.argentinadatos.com/v1/"
# Columna: (ruta de ArgentinaDatos, campo)
REFERENCIAS = {
    "TCC_Blue": ("cotizaciones/dolares/blue", "compra"),
    "TCV_Blue": ("cotizaciones/dolares/blue", "venta"),
    "TCC_Billete": ("cotizaciones/dolares/oficial", "compra"),
    "TCV_Billete": ("cotizaciones/dolares/oficial", "venta"),
    "TCC_Divisas": ("cotizaciones/dolares/mayorista", "compra"),
    "TCV_Divisas": ("cotizaciones/dolares/mayorista", "venta"),
    "TCV_MEP": ("cotizaciones/dolares/bolsa", "venta"),
    "Solidario": ("cotizaciones/dolares/tarjeta", "venta"),
    "riesgo_pais": ("finanzas/indices/riesgo-pais", "valor"),
}
ID_A3500, ID_BADLAR_TEA = 5, 140

TOLERANCIA = 0.05  # cuánto se puede apartar un dato corregido de su referencia
RACHA_RELLENO = 250  # días seguidos con el mismo valor: relleno de la carga histórica
RACHA_ESTANCADA = 5  # días seguidos con el mismo valor mientras la referencia se mueve
RACHA_EURO = 20  # el euro no tiene referencia: solo se marca una racha muy larga
DESVIO_GRANDE = 0.25  # billete o divisas a más de esto de dos fuentes: dato de otro día
DIFERENCIA_FED = 0.5  # puntos de tasa entre fed_tea y la EFFR de ese día
PARES = [("TCC_Blue", "TCV_Blue"), ("TCC_Billete", "TCV_Billete"), ("TCC_Divisas", "TCV_Divisas"),
         ("TCC_Euro", "TCV_Euro")]


# ── Reglas ────────────────────────────────────────────────────────────────────

def _rachas(serie: pd.Series) -> list[pd.Index]:
    """Las fechas de cada tramo de valores iguales y seguidos (los vacíos cortan el tramo)."""
    s = serie.dropna()
    grupos = (s != s.shift()).cumsum()
    return [g.index for _, g in s.groupby(grupos)]


def _escala(valor: float, referencia: float, tolerancia: float) -> int:
    """La potencia de 10 que separa el valor de su referencia, si al quitarla coinciden; si no, 0."""
    if not (valor > 0 and referencia > 0):
        return 0
    k = int(round(np.log10(valor / referencia)))
    return k if k and abs(valor / 10**k / referencia - 1) <= tolerancia else 0


def _a_la_fecha(serie: pd.Series, fechas: pd.Index) -> pd.Series:
    """El último dato de la serie a cada fecha (las tasas se publican con días de rezago)."""
    return serie.sort_index().reindex(serie.index.union(fechas)).ffill().reindex(fechas)


def correcciones(tabla: pd.DataFrame, ref: dict[str, pd.Series]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(tabla corregida, cambios) a partir de la tabla (Fecha como índice) y las referencias.

    `ref` trae una serie por columna de REFERENCIAS, más "a3500", "bcra_tea" y "fed_tea".
    Cada cambio: fecha, columna, antes, después y motivo. No toca la base.
    """
    nueva = tabla[NUMERICAS].astype(float).copy()
    cambios: list[tuple] = []

    def cambiar(fecha, columna, valor, motivo):
        antes = nueva.at[fecha, columna]
        if (pd.isna(antes) and pd.isna(valor)) or (pd.notna(antes) and pd.notna(valor) and np.isclose(antes, valor)):
            return
        nueva.at[fecha, columna] = valor
        cambios.append((fecha, columna, antes, valor, motivo))

    def referencia(columna) -> pd.Series:
        return ref[columna].reindex(nueva.index) if columna in ref else pd.Series(np.nan, index=nueva.index)

    # 1. Rellenos de la carga histórica: un valor repetido cientos de días. El último día del
    #    tramo es el primer dato real (se rellenó hacia atrás con él) y se conserva; el resto
    #    pasa a la referencia o, sin ella, queda vacío. La compra del blue vacía en esas fechas
    #    también se completa, para que compra y venta salgan de la misma fuente.
    # Solo cotizaciones: una tasa puede quedar fija cientos de días (la FED, 5,33% de 2023 a 2024)
    for columna in [c for c in NUMERICAS if c not in ("riesgo_pais", "fed_tea", "bcra_tea")]:
        for fechas in _rachas(nueva[columna]):
            if len(fechas) < RACHA_RELLENO:
                continue
            r = referencia(columna)
            for fecha in fechas[:-1]:
                cambiar(fecha, columna, r[fecha], f"relleno de la carga histórica ({len(fechas)} días con el mismo valor)")
            for compra, venta in PARES:
                if venta == columna:
                    rc = referencia(compra)
                    for fecha in fechas[:-1]:
                        if pd.isna(nueva.at[fecha, compra]) and pd.notna(rc[fecha]):
                            cambiar(fecha, compra, rc[fecha], "compra completada junto con la venta del relleno")

    # 2. Comas decimales corridas: el dato es la referencia por una potencia de 10 exacta. El
    #    billete y las divisas se comparan con el A3500 del BCRA, que tiene todos sus decimales
    #    desde 2002: ArgentinaDatos redondea el billete a pesos enteros hasta 2015.
    a3500 = referencia("a3500")
    oficiales = ("TCC_Billete", "TCV_Billete", "TCC_Divisas", "TCV_Divisas")
    for columna in REFERENCIAS:
        if columna in oficiales:
            continue
        r = referencia(columna)
        for fecha, valor in nueva[columna].dropna().items():
            k = _escala(valor, r[fecha], TOLERANCIA)
            if k:
                cambiar(fecha, columna, valor / 10**k, f"coma decimal corrida (x10^{k})")
    # En el billete y las divisas hay, además, un cero perdido después de la coma: 3,08 guardado
    # como 38 y 14,05 como 145 (de 2003 a 2017). Se prueban las dos lecturas y queda la más
    # cercana al A3500 entre las que dejan la compra por debajo de la venta de ese día
    pareja = {compra: (venta, True) for compra, venta in PARES} | {venta: (compra, False) for compra, venta in PARES}
    for columna in oficiales:
        otra, es_compra = pareja[columna]
        for fecha, valor in nueva[columna].dropna().items():
            base = a3500[fecha]
            if pd.isna(base) or abs(valor / base - 1) <= 0.5:
                continue
            opciones = {}
            k = int(round(np.log10(valor / base)))
            if k:
                opciones[f"coma decimal corrida (x10^{k})"] = valor / 10**k
            if valor >= 10 and valor == round(valor):
                opciones["cero perdido después de la coma (3,08 guardado como 38)"] = valor // 10 + (valor % 10) / 100
            contra = nueva.at[fecha, otra]
            if pd.notna(contra) and abs(contra / base - 1) <= 0.10:
                opciones = {m: v for m, v in opciones.items() if (v < contra if es_compra else v > contra)}
            if opciones:
                motivo, corregido = min(opciones.items(), key=lambda o: abs(o[1] / base - 1))
                if abs(corregido / base - 1) <= 0.10:
                    cambiar(fecha, columna, corregido, motivo)
    # El euro no tiene referencia: se compara con la mediana de los días vecinos, sin el día mismo
    for columna in ("TCC_Euro", "TCV_Euro"):
        s = nueva[columna].dropna()
        for i, (fecha, valor) in enumerate(s.items()):
            vecinos = pd.concat([s.iloc[max(i - 3, 0):i], s.iloc[i + 1:i + 4]])
            k = _escala(valor, vecinos.median(), 0.10) if len(vecinos) >= 3 else 0
            if k:
                cambiar(fecha, columna, valor / 10**k, f"coma decimal corrida (x10^{k}, contra los días vecinos)")
    for columna, tolerancia in (("bcra_tea", 0.15),):
        r = _a_la_fecha(ref[columna], nueva.index) if columna in ref else None
        if r is not None:
            for fecha, valor in nueva[columna].dropna().items():
                k = _escala(valor, r[fecha], tolerancia)
                if k:
                    cambiar(fecha, columna, valor / 10**k, f"coma decimal corrida (x10^{k})")

    # 3. Billete o divisas lejos de ArgentinaDatos y del A3500 a la vez, con las dos de acuerdo
    #    entre sí: el valor es de otro día (fechas con día y mes invertidos en la carga). Toma
    #    ArgentinaDatos solo si tiene decimales; redondeado a pesos enteros, queda vacío.
    for columna in oficiales:
        r = referencia(columna)
        for fecha, valor in nueva[columna].dropna().items():
            if not (pd.notna(r[fecha]) and pd.notna(a3500[fecha])):
                continue
            if (abs(valor / r[fecha] - 1) > DESVIO_GRANDE and abs(valor / a3500[fecha] - 1) > DESVIO_GRANDE
                    and abs(r[fecha] / a3500[fecha] - 1) <= 0.10):
                preciso = r[fecha] != round(r[fecha])
                cambiar(fecha, columna, r[fecha] if preciso else np.nan,
                        "lejos de ArgentinaDatos y del A3500: dato de otro día")

    # 4. Valores estancados: el scraper repitió el dato mientras la referencia se movía. Se
    #    conserva el primer día del tramo, que sí se leyó, y el resto pasa a la referencia.
    for columna in ("TCC_Blue", "TCV_Blue", "TCV_MEP", "Solidario"):
        r = referencia(columna)
        for fechas in _rachas(nueva[columna]):
            if not RACHA_ESTANCADA <= len(fechas) < RACHA_RELLENO:
                continue
            tramo = r[fechas].dropna()
            if len(tramo) < len(fechas) - 1 or tramo.max() / tramo.min() - 1 <= 0.01:
                continue
            for fecha in fechas[1:]:
                cambiar(fecha, columna, r[fecha], f"repetido {len(fechas)} días mientras el mercado se movía")
    for columna in ("TCC_Euro", "TCV_Euro"):
        for fechas in _rachas(nueva[columna]):
            if RACHA_EURO <= len(fechas) < RACHA_RELLENO:
                for fecha in fechas[1:]:
                    cambiar(fecha, columna, np.nan, f"repetido {len(fechas)} días: el scraper no se actualizó")

    # 5. La tasa de la FED que no coincide con la EFFR publicada para ese día
    if "fed_tea" in ref:
        r = _a_la_fecha(ref["fed_tea"], nueva.index)
        for fecha, valor in nueva["fed_tea"].dropna().items():
            if pd.notna(r[fecha]) and abs(valor - r[fecha]) > DIFERENCIA_FED:
                cambiar(fecha, "fed_tea", r[fecha], "no coincide con la EFFR de la FED")

    # 6. Compra mayor que venta: imposible. Queda vacío el de los dos que más se aparta de su semana
    for compra, venta in PARES:
        malos = nueva[nueva[compra] > nueva[venta]].index
        for fecha in malos:
            desvios = {}
            for columna in (compra, venta):
                vecinos = nueva[columna].drop(fecha).loc[fecha - pd.Timedelta(days=10):fecha + pd.Timedelta(days=10)]
                desvios[columna] = abs(nueva.at[fecha, columna] / vecinos.median() - 1) if len(vecinos) else 0
            peor = max(desvios, key=desvios.get)
            cambiar(fecha, peor, np.nan, "compra mayor que venta")

    tabla_cambios = pd.DataFrame(cambios, columns=["Fecha", "columna", "antes", "despues", "motivo"])
    return nueva, tabla_cambios


# ── Datos ─────────────────────────────────────────────────────────────────────

def bajar_referencias(desde: str) -> dict[str, pd.Series]:
    import httpx

    from reporte.config import settings
    from reporte.scrapers import agregados, fed
    from reporte.scrapers.utils import cliente_http, run_async

    ref = {}
    with httpx.Client(timeout=120) as cliente:
        cache = {}
        for columna, (ruta, campo) in REFERENCIAS.items():
            if ruta not in cache:
                cache[ruta] = pd.DataFrame(cliente.get(URL_ARGENTINADATOS + ruta).raise_for_status().json())
            datos = cache[ruta]
            ref[columna] = pd.Series(datos[campo].astype(float).values, index=pd.to_datetime(datos["fecha"])).sort_index()
            ref[columna] = ref[columna][~ref[columna].index.duplicated(keep="last")]
        r = cliente.get(fed.API_URL, params={"series_id": fed.SERIE_EFFR, "file_type": "json", "observation_start": desde,
                                             "api_key": settings.fed_api_key.get_secret_value()}).raise_for_status()
        obs = pd.DataFrame(r.json()["observations"])
        obs = obs[obs["value"] != "."]
        ref["fed_tea"] = pd.Series(obs["value"].astype(float).values, index=pd.to_datetime(obs["date"]))

    async def bcra():
        async with cliente_http(None, agregados.TIMEOUT) as c:
            return {clave: await agregados.fetch(agregados.Serie(clave, id_bcra, clave, "D", ""), c)
                    for clave, id_bcra in (("a3500", ID_A3500), ("bcra_tea", ID_BADLAR_TEA))}
    for clave, puntos in run_async(bcra()).items():
        serie = pd.Series(dict(puntos))
        serie.index = pd.to_datetime(serie.index)
        ref[clave] = serie.sort_index()
    return ref


def leer_tabla(engine) -> pd.DataFrame:
    from sqlalchemy import text

    with engine.connect() as con:
        con.execute(text("SET TRANSACTION READ ONLY"))
        tabla = pd.read_sql(text(f'SELECT * FROM "{TABLA}" ORDER BY "Fecha"'), con)
    tabla["Fecha"] = pd.to_datetime(tabla["Fecha"])
    return tabla.set_index("Fecha")


def aplicar(engine, cambios: pd.DataFrame) -> int:
    """Todos los cambios en una transacción: una tabla temporal y un UPDATE por columna."""
    from sqlalchemy import text

    # Una celda que cambiaron dos reglas queda con su último valor, que es el de la tabla corregida
    filas = cambios.drop_duplicates(["Fecha", "columna"], keep="last")
    valores = [(f.date(), c, None if pd.isna(v) else float(v)) for f, c, v in filas[["Fecha", "columna", "despues"]].values]
    actualizadas = 0
    with engine.begin() as con:
        con.execute(text("CREATE TEMP TABLE depuracion (fecha date, columna text, valor numeric) ON COMMIT DROP"))
        for inicio in range(0, len(valores), 500):  # de a 500 filas por INSERT, no una por viaje
            bloque = valores[inicio:inicio + 500]
            marcas = ", ".join(f"(:f{i}, :c{i}, :v{i})" for i in range(len(bloque)))
            parametros = {f"{letra}{i}": dato for i, fila in enumerate(bloque) for letra, dato in zip("fcv", fila)}
            con.execute(text(f"INSERT INTO depuracion VALUES {marcas}"), parametros)
        for columna in filas["columna"].unique():
            if columna not in NUMERICAS:  # el nombre va dentro del SQL: solo columnas conocidas
                raise ValueError(f"columna desconocida: {columna}")
            resultado = con.execute(text(
                f'UPDATE "{TABLA}" t SET "{columna}" = d.valor FROM depuracion d '
                f'WHERE d.columna = :columna AND t."Fecha" = d.fecha'), {"columna": columna})
            actualizadas += resultado.rowcount
        if actualizadas != len(filas):
            raise RuntimeError(f"se esperaban {len(filas)} celdas y se actualizaron {actualizadas}: no se aplica nada")
    return actualizadas


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--aplicar", action="store_true", help="Escribir los cambios en la base (antes, una copia)")
    args = parser.parse_args()

    from reporte import data_access

    engine = data_access.crear_engine()
    tabla = leer_tabla(engine)
    ref = bajar_referencias(f"{tabla.index[0]:%Y-%m-%d}")
    _, cambios = correcciones(tabla, ref)
    if cambios.empty:
        print("Sin errores para corregir.")
        return

    resumen = cambios.groupby(["columna", "motivo"]).agg(celdas=("Fecha", "size"), desde=("Fecha", "min"),
                                                          hasta=("Fecha", "max"))
    with pd.option_context("display.width", 200, "display.max_colwidth", 80, "display.max_rows", 200):
        print(resumen.to_string())
    celdas = len(cambios.drop_duplicates(["Fecha", "columna"]))
    print(f"\nTotal: {celdas} celdas en {cambios['Fecha'].nunique()} fechas")

    RESPALDOS.mkdir(exist_ok=True)
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    ruta_cambios = RESPALDOS / f"cambios-{marca}.csv"
    cambios.to_csv(ruta_cambios, index=False)
    print(f"Detalle: {ruta_cambios}")
    if not args.aplicar:
        print("No se escribió nada. Para aplicar: --aplicar")
        return

    ruta_copia = RESPALDOS / f"{TABLA}-{marca}.csv"
    tabla.reset_index().to_csv(ruta_copia, index=False)
    print(f"Copia de la tabla: {ruta_copia}")
    print(f"Aplicado: {aplicar(engine, cambios)} celdas actualizadas")


if __name__ == "__main__":
    main()
