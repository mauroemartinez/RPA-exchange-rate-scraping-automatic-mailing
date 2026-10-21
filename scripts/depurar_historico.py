"""Corrige los errores del histórico de Fact_Mercado_Macro contra fuentes independientes.

La auditoría de octubre de 2026 encontró, en la carga histórica y en años de scraping:
valores de relleno (el blue, el solidario y el euro repetidos miles de días con su primer
dato real), comas decimales corridas (MEP, divisas, billete y euro por 10, el solidario
hasta por 10^10), fechas con día y mes invertidos, el blue y el solidario sin moverse
durante semanas mientras el mercado se movía, y la tasa de la FED de 2023 mal cargada.

Uso:
    python scripts/depurar_historico.py             # muestra qué cambiaría; no escribe nada
    python scripts/depurar_historico.py --aplicar   # copia la tabla y aplica todo en una transacción

Las referencias son, en lo posible, las mismas fuentes que lee el scraper: el histórico del
Banco Nación para el billete, el de DolarHoy para la venta del blue y el de Ámbito para el
euro (y para el blue anterior a 2011, que DolarHoy no publica). Completan ArgentinaDatos
(mayorista, MEP, tarjeta y riesgo país), el A3500 y la BADLAR del BCRA, y la EFFR del New
York Fed. Una referencia sola no alcanza para reemplazar un dato propio (ArgentinaDatos
también tiene días mal cargados, y redondea): las reglas piden que el error sea evidente,
como una potencia de 10 exacta, o que lo confirme una segunda fuente. Cada cambio queda en
respaldos/ (ignorada por git) con su motivo, junto a la copia completa de la tabla. Se puede
volver a correr: si no encuentra nada, no cambia nada.
"""

import argparse
import io
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
# Columna: (ruta de ArgentinaDatos, campo). El billete, el blue y el euro salen de las fuentes del scraper
REFERENCIAS = {
    "TCC_Divisas": ("cotizaciones/dolares/mayorista", "compra"),
    "TCV_Divisas": ("cotizaciones/dolares/mayorista", "venta"),
    "TCV_MEP": ("cotizaciones/dolares/bolsa", "venta"),
    "Solidario": ("cotizaciones/dolares/tarjeta", "venta"),
    "riesgo_pais": ("finanzas/indices/riesgo-pais", "valor"),
}
RUTA_BLUE_ARGENTINADATOS = "cotizaciones/dolares/blue"
URL_BNA = "https://www.bna.com.ar/Cotizador/DescargarPorFecha"  # CSV, billetes desde 2003
URL_DOLARHOY = "https://dolarhoy.com/historico-dolar-blue/custom/{desde:%d-%m-%Y}_{hasta:%d-%m-%Y}"  # venta desde 2011
URL_AMBITO = "https://mercados.ambito.com//{ruta}/historico-general/{desde:%d-%m-%Y}/{hasta:%d-%m-%Y}"
URL_NY_FED = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json"
ID_A3500, ID_BADLAR_TEA = 5, 140
DOLAR_BNA = 22  # el dólar en el descargador del Banco Nación

TOLERANCIA = 0.05  # cuánto se puede apartar un dato corregido de su referencia
RACHA_RELLENO = 250  # días seguidos con el mismo valor: relleno de la carga histórica
RACHA_ESTANCADA = 5  # días seguidos con el mismo valor mientras la referencia se mueve
RACHA_EURO = 20  # el euro sin referencia: solo se marca una racha muy larga
DESVIO_GRANDE = 0.25  # billete o divisas a más de esto de dos fuentes: dato de otro día
DIFERENCIA_FED = 0.5  # puntos de tasa entre fed_tea y la EFFR de ese día
PARES = [("TCC_Blue", "TCV_Blue"), ("TCC_Billete", "TCV_Billete"), ("TCC_Divisas", "TCV_Divisas"),
         ("TCC_Euro", "TCV_Euro")]
BILLETE = ("TCC_Billete", "TCV_Billete")
TASAS = ("fed_tea", "bcra_tea")  # pueden repetirse de verdad: no prueban una copia


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


def _mala_lectura(valor: float, exacto: float) -> str | None:
    """Cómo se leyó mal `exacto` para guardarlo como `valor`, si es una de las lecturas conocidas."""
    for k in range(1, 5):
        if abs(valor / 10**k - exacto) < 0.0051:
            return f"coma decimal corrida (x10^{k})"
    if valor >= 10 and valor == round(valor) and abs(valor // 10 + valor % 10 / 100 - exacto) < 0.0051:
        return "cero perdido después de la coma (3,08 guardado como 38)"
    return None


def _a_la_fecha(serie: pd.Series, fechas: pd.Index) -> pd.Series:
    """El último dato de la serie a cada fecha (las tasas se publican con días de rezago)."""
    return serie.sort_index().reindex(serie.index.union(fechas)).ffill().reindex(fechas)


def referencias_blue(dolarhoy: pd.Series, ambito: pd.DataFrame,
                     argentinadatos: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(compra, venta) de referencia del blue.

    La venta es la de DolarHoy, la fuente del scraper; antes de 2011, que DolarHoy no publica,
    la de Ámbito (de 2011 a 2020 las dos son idénticas día por día). DolarHoy no publica la
    compra en su histórico: sale de la fuente cuya venta coincide con la de DolarHoy ese día,
    Ámbito (con centavos) y si no ArgentinaDatos, para que el par sea de una misma fuente. Si
    ninguna coincide, ese día no hay compra de referencia.
    """
    venta = dolarhoy.combine_first(ambito["venta"]).sort_index()
    compra = pd.Series(np.nan, index=venta.index)
    for fuente in (argentinadatos, ambito):  # la segunda pisa a la primera
        f = fuente.reindex(venta.index)
        # Compra igual a venta es real: de 2004 a 2011 el blue cotizó muchos días sin diferencia
        mismo_par = (f["venta"] - venta).abs().lt(0.005) & f["compra"].le(f["venta"])
        compra = compra.mask(mismo_par, f["compra"])
    return compra, venta


def correcciones(tabla: pd.DataFrame, ref: dict[str, pd.Series]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(tabla corregida, cambios) a partir de la tabla (Fecha como índice) y las referencias.

    `ref` trae una serie por columna (las de REFERENCIAS, el billete del Banco Nación, el blue
    y el euro), más "a3500", "bcra_tea" y "fed_tea". Cada cambio: fecha, columna, antes,
    después y motivo. No toca la base.
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
    for columna in [c for c in NUMERICAS if c not in ("riesgo_pais", *TASAS)]:
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

    # 2. Comas decimales corridas: el dato es la referencia por una potencia de 10 exacta.
    for columna in ("TCC_Blue", "TCV_Blue", "TCV_MEP", "Solidario", "riesgo_pais"):
        r = referencia(columna)
        for fecha, valor in nueva[columna].dropna().items():
            k = _escala(valor, r[fecha], TOLERANCIA)
            if k:
                cambiar(fecha, columna, valor / 10**k, f"coma decimal corrida (x10^{k})")
    # El billete viene del Banco Nación, que publica su histórico con el valor exacto: si lo
    # guardado es ese mismo número leído con la coma corrida o sin el cero que sigue a la coma
    # (3,08 guardado como 38, de 2003 a 2017), vuelve a él.
    for columna in BILLETE:
        r = referencia(columna)
        for fecha, valor in nueva[columna].dropna().items():
            lectura = _mala_lectura(valor, r[fecha]) if pd.notna(r[fecha]) else None
            if lectura:
                cambiar(fecha, columna, r[fecha], f"{lectura}, según el histórico del Banco Nación")
    # Sin el dato del banco (antes de 2003), y en las divisas, la guía es el A3500 del BCRA, que
    # tiene todos sus decimales desde 2002. Se prueban las dos lecturas y queda la más cercana
    # al A3500 entre las que dejan la compra por debajo de la venta de ese día
    a3500 = referencia("a3500")
    oficiales = (*BILLETE, "TCC_Divisas", "TCV_Divisas")
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
    # El euro sin referencia: se compara con la mediana de los días vecinos, sin el día mismo
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

    # 3. Día y mes invertidos: una fecha con día hasta 12 que tiene el billete exacto de la fecha
    #    con día y mes dados vuelta (el 11/01/2022, el del 01/11/2022), mientras el Banco Nación
    #    dice otro para ese día. Toda columna igual a la de esa otra fila se copió con ella:
    #    vuelve a su referencia o, sin ella, queda vacía.
    for fecha in nueva.index:
        if fecha.day > 12 or fecha.day == fecha.month:
            continue
        otra = pd.Timestamp(fecha.year, fecha.day, fecha.month)
        if otra not in nueva.index:
            continue
        bna_aca = [referencia(c)[fecha] for c in BILLETE]
        bna_otra = [referencia(c)[otra] for c in BILLETE]
        guardado = [nueva.at[fecha, c] for c in BILLETE]
        if pd.isna(bna_aca + bna_otra + guardado).any():
            continue
        if np.allclose(guardado, bna_aca) or not np.allclose(guardado, bna_otra):
            continue  # coincide con su día, o no es el billete de la otra fecha
        iguales = [c for c in NUMERICAS if c not in TASAS and pd.notna(nueva.at[fecha, c])
                   and pd.notna(nueva.at[otra, c]) and np.isclose(nueva.at[fecha, c], nueva.at[otra, c])]
        for columna in iguales:
            cambiar(fecha, columna, referencia(columna)[fecha], f"día y mes invertidos: es el dato del {otra:%d/%m/%Y}")

    # 4. Billete o divisas lejos de su referencia y del A3500 a la vez, con las dos de acuerdo
    #    entre sí: el valor es de otro día. El Banco Nación es exacto; de ArgentinaDatos solo
    #    se toma un dato con decimales: redondeado a pesos enteros, queda vacío.
    for columna in oficiales:
        r = referencia(columna)
        for fecha, valor in nueva[columna].dropna().items():
            if not (pd.notna(r[fecha]) and pd.notna(a3500[fecha])):
                continue
            if (abs(valor / r[fecha] - 1) > DESVIO_GRANDE and abs(valor / a3500[fecha] - 1) > DESVIO_GRANDE
                    and abs(r[fecha] / a3500[fecha] - 1) <= 0.10):
                preciso = columna in BILLETE or r[fecha] != round(r[fecha])
                cambiar(fecha, columna, r[fecha] if preciso else np.nan,
                        "lejos de su referencia y del A3500: dato de otro día")

    # 5. Valores estancados: el scraper repitió el dato mientras la referencia se movía. Se
    #    conserva el primer día del tramo, que sí se leyó, y el resto pasa a la referencia (o
    #    queda vacío el día que no la hay). La compra se mide con la venta, que tiene más fuentes.
    guia = {"TCC_Blue": "TCV_Blue", "TCC_Euro": "TCV_Euro"}
    for columna in ("TCC_Blue", "TCV_Blue", "TCV_MEP", "Solidario", "TCC_Euro", "TCV_Euro"):
        r, movimiento = referencia(columna), referencia(guia.get(columna, columna))
        for fechas in _rachas(nueva[columna]):
            if not RACHA_ESTANCADA <= len(fechas) < RACHA_RELLENO:
                continue
            tramo = movimiento[fechas].dropna()
            if len(tramo) < len(fechas) - 1 or tramo.max() / tramo.min() - 1 <= 0.01:
                continue
            for fecha in fechas[1:]:
                cambiar(fecha, columna, r[fecha], f"repetido {len(fechas)} días mientras el mercado se movía")
    # Una racha muy larga del euro sin referencia que la explique: la fuente dejó de publicar
    # (Ámbito no tuvo euro blue del 06/05 al 14/07/2026) y su página mostraba el último valor
    for columna in ("TCC_Euro", "TCV_Euro"):
        r = referencia(columna)
        for fechas in _rachas(nueva[columna]):
            if RACHA_EURO <= len(fechas) < RACHA_RELLENO:
                for fecha in fechas[1:]:
                    cambiar(fecha, columna, r[fecha], f"repetido {len(fechas)} días: la fuente no publicó")

    # 6. La tasa de la FED que no coincide con la EFFR publicada para ese día
    if "fed_tea" in ref:
        r = _a_la_fecha(ref["fed_tea"], nueva.index)
        for fecha, valor in nueva["fed_tea"].dropna().items():
            if pd.notna(r[fecha]) and abs(valor - r[fecha]) > DIFERENCIA_FED:
                cambiar(fecha, "fed_tea", r[fecha], "no coincide con la EFFR de la FED")

    # 7. Compra mayor que venta: imposible. El de los dos que más se aparta de su semana pasa a
    #    su referencia, y el otro también si con eso no alcanza. Sin un par de referencia
    #    válido, el que más se aparta queda vacío.
    for compra, venta in PARES:
        rc, rv = referencia(compra), referencia(venta)
        for fecha in nueva[nueva[compra] > nueva[venta]].index:
            desvios = {}
            for columna in (compra, venta):
                vecinos = nueva[columna].drop(fecha).loc[fecha - pd.Timedelta(days=10):fecha + pd.Timedelta(days=10)]
                desvios[columna] = abs(nueva.at[fecha, columna] / vecinos.median() - 1) if len(vecinos) else 0
            peor = max(desvios, key=desvios.get)
            if not (pd.notna(rc[fecha]) and pd.notna(rv[fecha]) and rc[fecha] <= rv[fecha]):
                cambiar(fecha, peor, np.nan, "compra mayor que venta, sin referencia: queda vacío")
                continue
            valor_ref = {compra: rc[fecha], venta: rv[fecha]}
            cambiar(fecha, peor, valor_ref[peor], "compra mayor que venta: pasa a la referencia")
            if nueva.at[fecha, compra] > nueva.at[fecha, venta]:
                otro = venta if peor == compra else compra
                cambiar(fecha, otro, valor_ref[otro], "compra mayor que venta: pasa a la referencia")

    # 8. Compra vacía con la venta igual a la de su referencia: la compra de esa misma fuente
    for compra, venta in PARES:
        rc, rv = referencia(compra), referencia(venta)
        faltan = nueva[compra].isna() & nueva[venta].notna() & rc.notna() & rv.notna()
        for fecha in nueva.index[faltan]:
            if abs(nueva.at[fecha, venta] - rv[fecha]) < 0.005 and rc[fecha] <= rv[fecha]:
                cambiar(fecha, compra, rc[fecha], "compra faltante: la de la misma fuente que la venta")

    tabla_cambios = pd.DataFrame(cambios, columns=["Fecha", "columna", "antes", "despues", "motivo"])
    return nueva, tabla_cambios


# ── Datos ─────────────────────────────────────────────────────────────────────
# Toda fecha se lee con su formato escrito: sin él, pandas toma 01/11/2022 como 11 de enero,
# el error que dejó el billete de noviembre de 2022 en enero, febrero, marzo, abril, julio,
# agosto y octubre.

_MESES_EN = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


def _fecha_dolarhoy(texto: str) -> pd.Timestamp:
    """'Mon Jan 03 2011 00:00:00 GMT-0300 (...)': el mes en inglés, leído sin depender del locale."""
    _, mes, dia, anio = texto.split()[:4]
    return pd.Timestamp(int(anio), _MESES_EN[mes], int(dia))


def _numero_ar(serie: pd.Series) -> pd.Series:
    return serie.str.strip().str.replace(".", "", regex=False).str.replace(",", ".", regex=False).astype(float)


def _ambito(cliente, ruta: str, desde: pd.Timestamp, hasta) -> pd.DataFrame:
    filas = cliente.get(URL_AMBITO.format(ruta=ruta, desde=desde, hasta=hasta)).raise_for_status().json()
    datos = pd.DataFrame(filas[1:], columns=[c.lower() for c in filas[0]])
    datos.index = pd.to_datetime(datos.pop("fecha"), format="%d/%m/%Y")
    datos = datos.apply(_numero_ar)
    return datos[~datos.index.duplicated()].sort_index()


def _argentinadatos(cliente, ruta: str) -> pd.DataFrame:
    datos = pd.DataFrame(cliente.get(URL_ARGENTINADATOS + ruta).raise_for_status().json())
    datos.index = pd.to_datetime(datos.pop("fecha"), format="%Y-%m-%d")
    return datos[~datos.index.duplicated(keep="last")].sort_index()


def bajar_referencias(desde: str) -> dict[str, pd.Series]:
    import httpx

    from reporte import fechas
    from reporte.scrapers import agregados
    from reporte.scrapers.utils import cliente_http, run_async

    hasta = fechas.hoy()
    ref = {}
    with httpx.Client(timeout=180, headers={"User-Agent": "Mozilla/5.0"}) as cliente:
        cache = {}
        for columna, (ruta, campo) in REFERENCIAS.items():
            if ruta not in cache:
                cache[ruta] = _argentinadatos(cliente, ruta)
            ref[columna] = cache[ruta][campo].astype(float)

        r = cliente.get(URL_BNA, params={"id": "billetes", "idMonedaDescarga": DOLAR_BNA, "fechaDesde": "01/01/2003",
                                         "fechaHasta": f"{hasta:%d/%m/%Y}"}).raise_for_status()
        bna = pd.read_csv(io.StringIO(r.text), sep=";", usecols=[1, 2, 3], names=["fecha", "compra", "venta"],
                          header=0, dtype=str)
        bna.index = pd.to_datetime(bna.pop("fecha").str.strip(), format="%d/%m/%Y")
        bna = bna.apply(_numero_ar)
        bna = bna[~bna.index.duplicated(keep="last")].sort_index()
        ref["TCC_Billete"], ref["TCV_Billete"] = bna["compra"], bna["venta"]

        puntos = cliente.get(URL_DOLARHOY.format(desde=pd.Timestamp("2011-01-01"), hasta=hasta)).raise_for_status().json()
        dolarhoy = pd.Series({_fecha_dolarhoy(p["x"]): float(p["y"]) for p in puntos}).sort_index()
        ambito_blue = _ambito(cliente, "dolar/informal", pd.Timestamp("2002-01-01"), hasta)
        blue_ad = _argentinadatos(cliente, RUTA_BLUE_ARGENTINADATOS)[["compra", "venta"]].astype(float)
        ref["TCC_Blue"], ref["TCV_Blue"] = referencias_blue(dolarhoy, ambito_blue, blue_ad)

        euro = _ambito(cliente, "euro/informal", pd.Timestamp("2002-01-01"), hasta)
        ref["TCC_Euro"], ref["TCV_Euro"] = euro["compra"], euro["venta"]

        tasas = cliente.get(URL_NY_FED, params={"startDate": desde, "endDate": f"{hasta:%Y-%m-%d}"}).raise_for_status()
        ref["fed_tea"] = pd.Series({pd.Timestamp(t["effectiveDate"]): float(t["percentRate"])
                                    for t in tasas.json()["refRates"] if t.get("percentRate") is not None}).sort_index()

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
