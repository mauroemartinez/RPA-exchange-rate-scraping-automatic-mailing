"""Preparación de los datos de los gráficos del reporte y su generación.

La preparación (preparar_*) es lógica pura y no cambia con el diseño. El dibujo de los seis
gráficos de marca (tipos de cambio, riesgo país, inflación, variaciones, agregados y deuda)
vive en reporte/marca/graficos.py: vidrio azul de GlobalAIze, sin naranja, con la tipografía de
la marca. Acá quedan los grafico_* de siempre como puerta de entrada. BTC conserva a propósito
su estética crypto y se dibuja en este módulo.

Cada gráfico se dibuja sobre una Figure propia, sin pyplot, y dentro de su propio rc_context,
así que ningún estilo se filtra al siguiente. Los meses salen en español sin usar el locale del
sistema (ver fechas.MESES_ABREV).
"""

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib as mpl
import matplotlib.dates as mdates
import pandas as pd
import seaborn as sns
from matplotlib.artist import setp
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from reporte import transformations
from reporte.fechas import mes_abreviado
from reporte.transformations import etiqueta_mes

log = logging.getLogger(__name__)

# Nombres de archivo y orden en el mail: el template los referencia como
# cid:image1 .. cid:image6, en este orden. Los dos nuevos van al final para que
# los cid de los cuatro de siempre no cambien.
TIPOS_DE_CAMBIO = "Tipos de Cambio.jpg"
RIESGO_PAIS = "Riesgo País.jpg"
INFLACION = "Gráficos Inflación.jpg"
VARIACIONES = "Variaciones.jpg"
BTC = "Gráfico BTC.jpg"
AGREGADOS = "Agregados Monetarios.jpg"
DEUDA = "Deuda en Dólares.jpg"
ORDEN_EN_MAIL = (TIPOS_DE_CAMBIO, RIESGO_PAIS, INFLACION, VARIACIONES, AGREGADOS, DEUDA, BTC)


def cid(nombre: str) -> str:
    """El Content-ID del gráfico en el mail ('image1'...): sale de su lugar en ORDEN_EN_MAIL."""
    return f"image{ORDEN_EN_MAIL.index(nombre) + 1}"

COTIZACIONES_A_MOSTRAR = 25

# Inicio del período del gráfico de variaciones acumuladas. Cambiarlo cuando
# cambie el período de referencia.
FECHA_INICIO_VARIACIONES = "2025-07-01"

@contextmanager
def _estilo_base():
    """Estilo de partida de todos los gráficos: el de matplotlib más sns.set(style='ticks')."""
    with mpl.rc_context():
        mpl.rcdefaults()
        sns.set_theme(style="ticks")
        yield


def _formato_mes(fmt: str) -> FuncFormatter:
    """Equivalente de mdates.DateFormatter(fmt) para '%b/%y' y '%b %Y', con meses en español."""
    separador, anio = {"%b/%y": ("/", "%y"), "%b %Y": (" ", "%Y")}[fmt]

    def formatear(x, pos=None):
        fecha = mdates.num2date(x)
        return f"{mes_abreviado(fecha)}{separador}{fecha.strftime(anio)}"

    return FuncFormatter(formatear)


def _guardar(fig: Figure, carpeta: Path, nombre: str, **kwargs) -> Path:
    ruta = Path(carpeta) / nombre
    fig.savefig(ruta, **kwargs)
    log.info("Gráfico guardado: %s", ruta.name)
    return ruta


# ── Tipos de cambio y riesgo país ────────────────────────────────────────────

def preparar_datos(df: pd.DataFrame) -> pd.DataFrame:
    """El histórico de más viejo a más nuevo, con Fecha como texto 'dd/mm/yy' (celda 39)."""
    data = df.copy().iloc[::-1]
    data["Fecha"] = pd.to_datetime(data["Fecha"], dayfirst=False, errors="coerce")
    data["Fecha"] = data["Fecha"].dt.strftime("%d/%m/%y")
    return data


def _step_riesgo_pais(valor_max: float) -> tuple[float, float]:
    """Paso de ticks del riesgo país según el máximo de la ventana mostrada.

    Antes estaba fijo en 500, pensado para cuando el riesgo país superaba los 2000
    puntos. Con valores por debajo de 1000 ese paso escondía la variación diaria.
    """
    if valor_max <= 300:
        return 25, 12.5
    elif valor_max <= 1000:
        return 100, 50
    elif valor_max <= 2000:
        return 250, 100
    else:
        return 500, 200


# ── Variaciones acumuladas ───────────────────────────────────────────────────

def preparar_variaciones(
    data: pd.DataFrame, inflacion: pd.DataFrame, fecha_inicio: str = FECHA_INICIO_VARIACIONES
) -> pd.DataFrame:
    """Solidario, blue e inflación acumulados desde fecha_inicio (celda 41).

    `data` es la salida de preparar_datos() e `inflacion` la serie mensual que se
    cruza por fecha con las cotizaciones. Tiene que ser la serie completa, o al
    menos cubrir desde fecha_inicio: el notebook cruzaba solo los últimos 12 meses
    y, pasado un año desde fecha_inicio, la inflación acumulada empezaba meses
    después que el dólar (en octubre de 2026 arrancaba en septiembre de 2025
    contra julio de 2025), así que el gráfico comparaba períodos distintos.
    """
    data = data.copy()
    # preparar_datos() dejó las fechas como 'dd/mm/yy'; con el formato explícito
    # pandas no tiene que adivinarlo fila por fila (y no avisa que lo está haciendo)
    data["Fecha"] = pd.to_datetime(data["Fecha"], format="%d/%m/%y", errors="coerce")

    va = data.merge(inflacion[["Fecha", "Inflación Mensual"]], on=["Fecha"], how="outer")
    # Después del merge, las fechas con inflación pero sin cotización quedan al final
    va.sort_values("Fecha", inplace=True)
    # Índice desde cero: las etiquetas "cada 25 filas" del gráfico arrancan en el
    # inicio del período y no dependen de cuánta historia vino antes
    va = va[va["Fecha"] >= pd.to_datetime(fecha_inicio)].reset_index(drop=True)

    for column in ["Variación Solidario", "Variación TCV Blue", "Inflación Mensual"]:
        if column == "Inflación Mensual":
            va[f"{column} Acumulada"] = ((1 + va[column] / 100).cumprod() - 1) * 100
        else:
            va[f"{column} Acumulada"] = ((1 + va[column]).cumprod() - 1) * 100
    return va


# ── Inflación ────────────────────────────────────────────────────────────────

def preparar_inflacion(inflacion_12: pd.DataFrame) -> pd.DataFrame:
    """Los meses del gráfico, de más viejo a más nuevo, rotulados 'sep/2025' (celda 42)."""
    datos = inflacion_12.copy()
    datos["Fecha"] = [etiqueta_mes(f) for f in datos["Fecha"]]
    return datos


# ── BTC ──────────────────────────────────────────────────────────────────────

DIAS_BTC = 365
# Margen extra de descarga para que las medias móviles y la volatilidad ya
# tengan valor desde el primer día que se muestra.
MARGEN_BTC = 40


def rango_btc(ahora: datetime) -> tuple[datetime, datetime]:
    """(desde, hasta) para descargar BTC, con el margen de los rolling incluido."""
    return ahora - timedelta(days=DIAS_BTC) - timedelta(days=MARGEN_BTC), ahora


def preparar_btc(crudo: pd.DataFrame, ahora: datetime) -> pd.DataFrame:
    """Medias móviles y volatilidad sobre lo que devuelve yfinance, recortado a 12 meses."""
    btc_df = crudo.reset_index()
    if isinstance(btc_df.columns, pd.MultiIndex):
        btc_df.columns = btc_df.columns.get_level_values(0)

    btc_df["index"] = pd.to_datetime(btc_df["index"])
    btc_df = btc_df.set_index("index")
    btc_df.index.name = "Date"

    btc_df["MA7"] = btc_df["Close"].rolling(window=7).mean()
    btc_df["MA30"] = btc_df["Close"].rolling(window=30).mean()
    btc_df["Volatility"] = btc_df["Close"].pct_change().rolling(window=20).std() * 100

    # Recorte a los 12 meses visibles, con las medias ya completas
    return btc_df[btc_df.index >= ahora - timedelta(days=DIAS_BTC)]


def grafico_btc(btc_df: pd.DataFrame, carpeta: Path) -> Path:
    """Precio de BTC con medias de 7 y 30 días y volatilidad de 20 días (celda 43)."""
    # .iloc[-1] es la ÚLTIMA vela disponible, no necesariamente la de hoy: yfinance
    # cierra el día según UTC y puede venir con retraso. Por eso dice 'Última cotización'.
    price_last = float(btc_df["Close"].iloc[-1])
    price_last_date = btc_df.index[-1]
    price_max = float(btc_df["Close"].max())
    price_min = float(btc_df["Close"].min())
    volatility_current = float(btc_df["Volatility"].iloc[-1])

    with _estilo_base():
        sns.set_theme(style="darkgrid", palette="husl")
        mpl.style.use("dark_background")

        fig = Figure(figsize=(16, 10), facecolor="#0a0a0a")
        ax1, ax2 = fig.subplots(2, 1, gridspec_kw={"height_ratios": [3, 1]})

        for ax in [ax1, ax2]:
            ax.set_facecolor("#0a0a0a")
            ax.grid(True, alpha=0.2, color="#333333", linestyle="-", linewidth=0.5)

        ax1.fill_between(btc_df.index, btc_df["Close"], alpha=0.1, color="#00ff41")
        ax1.plot(btc_df.index, btc_df["Close"], color="#00ff41", linewidth=2.5, label="Precio BTC", zorder=5)
        ax1.plot(btc_df.index, btc_df["MA7"], color="#FFD700", linewidth=2.2, linestyle="-.", label="Media 7 días", alpha=0.9, zorder=4)
        ax1.plot(btc_df.index, btc_df["MA30"], color="#FF6B6B", linewidth=2.2, linestyle=":", label="Media 30 días", alpha=0.85, zorder=4)

        ax1.xaxis.set_major_locator(mdates.MonthLocator(bymonthday=1))
        ax1.xaxis.set_major_formatter(_formato_mes("%b %Y"))
        ax1.xaxis.set_minor_locator(mdates.MonthLocator(bymonthday=15))
        setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha="right")
        ax1.set_xlim(btc_df.index[0], btc_df.index[-1])
        ax1.set_ylim(bottom=0)

        ax1.set_title("BTC/USD, últimos 12 meses", fontsize=20, fontweight="bold", color="#00ff41", pad=20)
        ax1.set_ylabel("USD/BTC", fontsize=13, color="#00ff41", fontweight="bold")

        legend1 = ax1.legend(
            loc="upper left", fontsize=12, framealpha=0.95, edgecolor="#00ff41", facecolor="#0a0a0a",
            labelcolor="#ffffff", title="Indicadores", title_fontsize=12,
        )
        legend1.get_title().set_color("#00ff41")

        ax2.fill_between(btc_df.index, btc_df["Volatility"], alpha=0.3, color="#FF6B6B")
        ax2.plot(btc_df.index, btc_df["Volatility"], color="#FF6B6B", linewidth=2, label="Volatilidad (20d)")
        ax2.set_ylabel("Volatilidad (%)", fontsize=12, color="#FF6B6B", fontweight="bold")
        ax2.xaxis.set_major_locator(mdates.MonthLocator(bymonthday=1))
        ax2.xaxis.set_major_formatter(_formato_mes("%b %Y"))
        ax2.xaxis.set_minor_locator(mdates.MonthLocator(bymonthday=15))
        setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha="right")
        ax2.set_xlim(btc_df.index[0], btc_df.index[-1])
        ax2.set_ylim(bottom=0)
        ax2.legend(loc="upper left", fontsize=11, framealpha=0.95, edgecolor="#FF6B6B", facecolor="#0a0a0a", labelcolor="#ffffff")

        for ax in [ax1, ax2]:
            ax.spines["bottom"].set_color("#00ff41")
            ax.spines["left"].set_color("#00ff41")
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            ax.minorticks_on()
            ax.tick_params(
                axis="both", which="major", direction="in", length=8, width=1.5, color="#00ff41",
                labelcolor="#ffffff", labelsize=10, bottom=True, left=True,
            )
            ax.tick_params(axis="both", which="minor", direction="in", length=4, width=1.0, color="#00ff41", bottom=True, left=True)

        kpi_text = (
            f"Última cotización: ${price_last:,.0f}  ({price_last_date:%d/%m/%y})\n"
            f"Máximo: ${price_max:,.0f}\n"
            f"Mínimo: ${price_min:,.0f}\n"
            f"Volatilidad: {volatility_current:.2f}%"
        )
        ax1.text(
            0.98, 0.97, kpi_text, transform=ax1.transAxes, fontsize=11, fontweight="bold",
            bbox=dict(boxstyle="round,pad=1", facecolor="#1a1a1a", edgecolor="#00ff41", alpha=0.9, linewidth=2),
            ha="right", va="top", color="#00ff41", family="monospace",
        )

        fig.tight_layout()
        return _guardar(fig, carpeta, BTC, dpi=150, facecolor="#0a0a0a", edgecolor="none", bbox_inches="tight")


# ── Agregados monetarios (fase 3) ────────────────────────────────────────────

# Series del panel de niveles y del de variación interanual, con su rótulo
NIVELES = {"base_monetaria": "Base monetaria", "circulacion_monetaria": "Circulación monetaria", "m2": "M2"}
INTERANUALES = {"base_monetaria": "Base monetaria", "m2": "M2", "m3": "M3 (mensual)"}
# Lo que tiene que haber bajado bien para dibujar el gráfico
CLAVES_AGREGADOS = (*dict.fromkeys([*NIVELES, *INTERANUALES]), "inflacion_interanual")


def preparar_agregados(series: dict, hoy) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(niveles en billones de ARS, variación interanual), los dos del último año.

    `series` es lo que devuelve scrapers.agregados.descargar(). Los niveles se
    pasan de millones a billones solo para el gráfico: en la base quedan en la
    unidad de la fuente.
    """
    # Un año en los dos paneles: con dos, la variación interanual de fines de 2024
    # (más de 200%) aplastaba la escala justo donde está la comparación que importa
    corte = pd.Timestamp(hoy) - pd.DateOffset(years=1)

    niveles = []
    for clave, rotulo in NIVELES.items():
        df = transformations.serie_a_frame(series[clave])
        df = df[df["Fecha"] >= corte].assign(serie=rotulo, billones=lambda d: d["valor"] / 1e6)
        niveles.append(df)

    interanuales = []
    for clave, rotulo in {**INTERANUALES, "inflacion_interanual": "Inflación interanual"}.items():
        if clave == "inflacion_interanual":
            # La misma interanual que la tabla del mail (compuesta con las mensuales)
            df = transformations.serie_a_frame(transformations.inflacion_interanual(series))
            df = df.rename(columns={"valor": "interanual"})
        else:
            df = transformations.interanual_por_fecha(series[clave])
        interanuales.append(df[df["Fecha"] >= corte].assign(serie=rotulo))

    return pd.concat(niveles, ignore_index=True), pd.concat(interanuales, ignore_index=True)


# ── Deuda, en dólares (fase 3) ───────────────────────────────────────────────

# Meses de deuda bruta del Tesoro en el panel de arriba: dos años muestran la
# tendencia sin aplastar los últimos meses
MESES_DEUDA_BRUTA = 24
# Las series del BCRA van en pesos y se pasan a dólares con el mayorista de cada día
CLAVES_DEUDA_BCRA = (
    "prestamos_sector_privado", "letras_bcra_pesos", "letras_bcra_moneda_extranjera",
    "adelantos_transitorios", "tipo_cambio_mayorista",
)
LETRAS = "Letras del BCRA (en pesos y en dólares)"
ADELANTOS = "Adelantos transitorios del BCRA al Tesoro"


def _sumar_por_fecha(*series: list[tuple]) -> list[tuple]:
    """La suma de varias series fecha por fecha, arrastrando el último valor de la que no publicó ese día."""
    presentes = [transformations.serie_a_frame(s).set_index("Fecha")["valor"] for s in series if s]
    if not presentes:
        return []
    # El último valor se arrastra unos pocos días (feriados, publicaciones desfasadas), no
    # para siempre: una serie que dejó de publicar no se sigue sumando como si fuera de hoy
    suma = pd.concat(presentes, axis=1).sort_index().ffill(limit=5).dropna().sum(axis=1)
    return [(fecha.date(), float(valor)) for fecha, valor in suma.items()]


def preparar_deuda(series: dict, hoy, provisorios=frozenset()) -> dict:
    """Los tres paneles del gráfico de deuda, en miles de millones de USD; un panel sin datos queda en None.

    `tesoro` es la deuda bruta mensual de los últimos MESES_DEUDA_BRUTA meses, con
    una columna que marca los provisorios. `prestamos` y `bcra` son las series
    diarias del último año pasadas de pesos a dólares con el mayorista de cada día;
    `bcra` trae las letras (pesos más moneda extranjera) y los adelantos al Tesoro.
    """
    corte = pd.Timestamp(hoy) - pd.DateOffset(years=1)
    datos: dict = {"tesoro": None, "prestamos": None, "bcra": None}

    if series.get("deuda_bruta_tesoro"):
        tesoro = transformations.serie_a_frame(series["deuda_bruta_tesoro"]).tail(MESES_DEUDA_BRUTA)
        tesoro = tesoro.assign(
            miles_de_millones=tesoro["valor"] / 1e3, provisorio=tesoro["Fecha"].dt.date.isin(set(provisorios)),
            # El dato es el saldo al último día del mes; se dibuja al principio del mes
            # para que quede sobre su rótulo y no pegado al del mes siguiente
            Mes=tesoro["Fecha"].dt.to_period("M").dt.to_timestamp(),
        )
        datos["tesoro"] = tesoro.reset_index(drop=True)

    cambio = series.get("tipo_cambio_mayorista")
    if not cambio:
        return datos

    def en_dolares(puntos: list[tuple]) -> pd.DataFrame | None:
        if not puntos:
            return None
        df = transformations.a_dolares(puntos, cambio)
        df = df[df["Fecha"] >= corte]
        return None if df.empty else df.assign(miles_de_millones=df["usd"] / 1e3).reset_index(drop=True)

    datos["prestamos"] = en_dolares(series.get("prestamos_sector_privado"))
    partes = {
        LETRAS: en_dolares(_sumar_por_fecha(series.get("letras_bcra_pesos"), series.get("letras_bcra_moneda_extranjera"))),
        ADELANTOS: en_dolares(series.get("adelantos_transitorios")),
    }
    partes = [df.assign(serie=rotulo) for rotulo, df in partes.items() if df is not None]
    datos["bcra"] = pd.concat(partes, ignore_index=True) if partes else None
    return datos


# ── Los seis gráficos de marca (todos menos BTC) ─────────────────────────────
# El dibujo vive en reporte/marca/graficos.py; acá quedan los nombres de siempre, para que el
# pipeline, el reenvío manual y los scripts no cambien. Los import van adentro: graficos usa
# la preparación de datos de este módulo.

def _de_marca(nombre: str, carpeta: Path, dibujar, diapositiva=None) -> Path:
    from reporte.marca import estilo, graficos

    with estilo.contexto():
        return graficos.guardar(dibujar(), nombre, carpeta, diapositiva)


def grafico_tipos_de_cambio(data: pd.DataFrame, carpeta: Path, n: int = COTIZACIONES_A_MOSTRAR) -> Path:
    """Cotizaciones paralelas y oficiales de las últimas n ruedas, un panel arriba del otro."""
    from reporte.marca import graficos

    return _de_marca(TIPOS_DE_CAMBIO, carpeta, lambda: graficos.tipos_de_cambio(data, n))


def grafico_riesgo_pais(data: pd.DataFrame, carpeta: Path, n: int = COTIZACIONES_A_MOSTRAR) -> Path:
    """Riesgo país de las últimas n ruedas: barras con el máximo y el mínimo resaltados y la variación diaria."""
    from reporte.marca import graficos

    return _de_marca(RIESGO_PAIS, carpeta, lambda: graficos.riesgo_pais(data, n))


def grafico_variaciones(variacion_acumulada: pd.DataFrame, carpeta: Path) -> Path:
    """Variaciones acumuladas de solidario y blue contra la inflación."""
    from reporte.marca import graficos

    return _de_marca(VARIACIONES, carpeta, lambda: graficos.variaciones(variacion_acumulada))


def grafico_inflacion(inflacion: pd.DataFrame, carpeta: Path) -> Path:
    """Inflación mensual en barras e interanual en línea, en dos ejes."""
    from reporte.marca import graficos

    return _de_marca(INFLACION, carpeta, lambda: graficos.inflacion(inflacion))


def grafico_agregados(niveles: pd.DataFrame, interanual: pd.DataFrame, carpeta: Path) -> Path:
    """Niveles de base monetaria, circulación y M2, y su variación interanual contra la inflación."""
    from reporte.marca import graficos

    return _de_marca(
        AGREGADOS, carpeta, lambda: graficos.agregados(niveles, interanual),
        lambda: graficos.agregados(niveles, interanual, con_titulo=False, tamano=graficos.TAMANO_DIAPOSITIVA),
    )


def grafico_deuda(datos: dict, carpeta: Path) -> Path:
    """Deuda bruta del Tesoro, préstamos al sector privado y deuda del BCRA, todo en dólares."""
    from reporte.marca import graficos

    return _de_marca(
        DEUDA, carpeta, lambda: graficos.deuda(datos),
        lambda: graficos.deuda(datos, con_titulo=False, tamano=graficos.TAMANO_DIAPOSITIVA),
    )
