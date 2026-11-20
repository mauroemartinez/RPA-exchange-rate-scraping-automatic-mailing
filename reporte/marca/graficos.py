"""Los seis gráficos del reporte (todos menos BTC) con la estética de GlobalAIze.

MODO PRUEBA, ver estilo.py. Reusan la preparación de datos de reporte/charts.py
(preparar_datos, preparar_variaciones, preparar_agregados, preparar_deuda...), que
no cambia: solo se redibuja. Cada función devuelve una Figure transparente de
(ancho x alto) pulgadas; `guardar` la monta sobre su panel de vidrio para el mail y
deja también la versión transparente que va en la presentación.

Diferencias de diseño contra los gráficos de siempre:
  * fondo de vidrio azul, tinta clara y la paleta de series de la marca (sin naranja);
  * título en Newsreader, alineado a la izquierda, con una línea de contexto debajo;
  * etiquetas directas al final de cada serie en vez de recuadros cada cinco puntos;
  * números con el formato argentino (1.234,5);
  * rojo y verde solo para subas y bajas, siempre con flecha.
"""

import io
import logging
import warnings
from collections.abc import Callable
from pathlib import Path

import matplotlib.dates as mdates
import pandas as pd
from matplotlib import font_manager as fm
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter, MultipleLocator

from reporte import charts
from reporte.marca import estilo
from reporte.marca.estilo import (
    AZUL,
    BUENO,
    CIAN,
    ELEVADA,
    MALO,
    OLIVA,
    SECUNDARIO,
    TENUE,
    TINTA,
    VERDE_AZULADO,
    VIOLETA,
)

log = logging.getLogger(__name__)

TAMANO_DIAPOSITIVA = (8.2, 7.0)  # pulgadas de agregados y deuda cuando van en una diapositiva
DPI = 200  # con 1 pulgada = 100 px lógicos del vidrio (K = 2)


# ── Utilidades ───────────────────────────────────────────────────────────────

def es(valor: float, decimales: int = 0) -> str:
    """Formato argentino: 1234.5 con un decimal da '1.234,5'."""
    return f"{valor:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _formato_es(decimales: int = 0, sufijo: str = "") -> FuncFormatter:
    return FuncFormatter(lambda v, _: f"{es(v, decimales)}{sufijo}")


def _fuente(peso: str = "normal", tamanio: float = 10, familia=None) -> fm.FontProperties:
    return fm.FontProperties(family=familia or estilo.TEXTO, weight=peso, size=tamanio)


def _figura(ancho: float, alto: float, titulo: str | None, contexto: str | None, paneles: int = 1,
            alturas: list[float] | None = None, margen_derecho: float = 0.075, leyenda: bool = True):
    """Figure transparente con título arriba a la izquierda y los paneles ya acomodados."""
    fig = Figure(figsize=(ancho, alto))
    arriba = 0.0
    if titulo:
        fig.text(0.04, 1 - 0.30 / alto, titulo, fontproperties=_fuente("medium", 22, estilo.TITULO), color=TINTA, va="top")
        arriba = 0.62
    if contexto:
        fig.text(0.04, 1 - (0.30 + 0.46) / alto, contexto, fontproperties=_fuente("normal", 10.5), color=TENUE, va="top")
        arriba = 0.95
    # Lo que ocupa arriba del primer eje: el título del panel y la leyenda (varios paneles) o solo la leyenda
    arriba += 0.25 + (0.85 if paneles > 1 else 0.4 if leyenda else 0.0)
    superior = 1 - arriba / alto
    inferior = 0.10 if paneles == 1 else 0.08
    # El hueco entre paneles es fijo, en pulgadas (rótulos del eje, título y leyenda del panel de abajo): hspace es una fracción
    # de la altura de un panel, así que se calcula para que el hueco no dependa del tamaño de la figura
    hueco = 1.05
    alto_panel = (alto * (superior - inferior) - (paneles - 1) * hueco) / paneles
    ejes = fig.subplots(paneles, 1, gridspec_kw={"height_ratios": alturas or [1] * paneles, "hspace": hueco / alto_panel if paneles > 1 else 0})
    fig.subplots_adjust(left=0.085, right=1 - margen_derecho, top=superior, bottom=inferior)
    return fig, ejes


def _subtitulo(ax, texto: str) -> None:
    ax.set_title(texto, loc="left", fontproperties=_fuente("semibold", 12.5), color=TINTA, pad=32)


def _leyenda(ax, ncol: int = 5, **kw) -> None:
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=ncol, handlelength=1.6, columnspacing=1.4,
              borderaxespad=0.2, prop=_fuente("normal", 9.5), **kw)


def _caja(color: str) -> dict:
    return dict(boxstyle="round,pad=0.28,rounding_size=0.45", facecolor=ELEVADA, edgecolor=color, linewidth=1.1)


def _etiquetas_finales(ax, x, finales: list[tuple[float, str, str]], separacion: float = 17) -> None:
    """El valor de cada serie a la derecha de su último punto, sin que se pisen.

    `finales` es [(valor, texto, color)]. Las etiquetas se ordenan por altura y se
    empujan hacia arriba hasta dejar `separacion` puntos entre una y otra.
    """
    ax.figure.canvas.draw_idle()
    base = ax.transData
    items = sorted(((base.transform((0, v))[1], v, t, c) for v, t, c in finales), key=lambda i: i[0])
    escala = 72 / ax.figure.dpi
    anterior = None
    for y_px, valor, texto, color in items:
        y_pt = y_px * escala
        if anterior is not None and y_pt - anterior < separacion:
            y_pt = anterior + separacion
        ax.annotate(
            texto, xy=(x, valor), xytext=(9, y_pt - y_px * escala), textcoords="offset points", va="center", ha="left",
            fontproperties=_fuente("semibold", 9.5), color=color, bbox=_caja(color), annotation_clip=False,
            arrowprops=dict(arrowstyle="-", color=color, lw=0.8, alpha=0.6, shrinkA=0, shrinkB=2),
        )
        anterior = y_pt


def _eje_ruedas(ax, fechas: list[str], cada: int = 3) -> None:
    """Eje de posiciones (0, 1, 2...) con la fecha 'dd/mm' cada `cada` ruedas: las ruedas no tienen fines de semana."""
    n = len(fechas)
    ax.set_xlim(-0.6, n - 1 + 0.6)
    ax.xaxis.set_major_locator(MultipleLocator(cada))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: fechas[int(round(x))][:5] if 0 <= int(round(x)) < n else ""))
    ax.set_xlabel("")
    ax.grid(axis="x", visible=False)


def _flecha(variacion: float) -> tuple[str, str]:
    """(texto, color) de una variación: flecha y color, subir es malo y bajar es bueno (criterio macro del mail)."""
    if round(variacion, 1) == 0:
        return "0%", SECUNDARIO
    return (f"▲{es(variacion, 1)}%", MALO) if variacion > 0 else (f"▼{es(abs(variacion), 1)}%", BUENO)


# ── Tipos de cambio ──────────────────────────────────────────────────────────

PARALELAS = [("TCV_Euro", "Euro blue", OLIVA, "-"), ("TCV_Blue", "Blue venta", CIAN, "-"),
             ("TCC_Blue", "Blue compra", CIAN, "--"), ("TCV_MEP", "MEP", VIOLETA, "-"),
             ("Solidario", "Solidario", VERDE_AZULADO, "-")]
OFICIALES = [("TCV_Billete", "Billete venta", CIAN, "-"), ("TCC_Billete", "Billete compra", CIAN, "--"),
             ("TCV_Divisas", "Divisas venta", VIOLETA, "-"), ("TCC_Divisas", "Divisas compra", VIOLETA, "--")]


def tipos_de_cambio(data: pd.DataFrame, n: int = charts.COTIZACIONES_A_MOSTRAR, con_titulo: bool = True) -> Figure:
    """Paralelas y oficiales de las últimas n ruedas, un panel arriba del otro."""
    ultimos = data.tail(n).reset_index(drop=True)
    fechas = ultimos["Fecha"].tolist()
    fig, ax = _figura(10, 9.4, f"Tipos de cambio, últimas {len(ultimos)} ruedas" if con_titulo else None,
                      "Pesos por dólar, a la venta salvo donde dice compra. Línea punteada: precio de compra." if con_titulo else None,
                      paneles=2, margen_derecho=0.13)
    for axis, titulo, columnas in ((ax[0], "Cotizaciones paralelas", PARALELAS), (ax[1], "Cotizaciones oficiales (BNA)", OFICIALES)):
        _subtitulo(axis, titulo)
        for col, rotulo, color, trazo in columnas:
            axis.plot(ultimos.index, ultimos[col], color=color, linestyle=trazo, linewidth=2.2, marker="o" if trazo == "-" else None,
                      markersize=3.2, label=rotulo, solid_capstyle="round")
        _eje_ruedas(axis, fechas)
        alto, bajo = ultimos[[c for c, *_ in columnas]].max().max(), ultimos[[c for c, *_ in columnas]].min().min()
        margen = (alto - bajo) * 0.08 or 1
        axis.set_ylim(bajo - margen, alto + margen)
        axis.yaxis.set_major_formatter(_formato_es())
        _leyenda(axis, ncol=len(columnas))
        _etiquetas_finales(axis, len(ultimos) - 1, [(ultimos[c].iloc[-1], es(ultimos[c].iloc[-1], 0), color) for c, _, color, _ in columnas])
    return fig


# ── Riesgo país ──────────────────────────────────────────────────────────────

def riesgo_pais(data: pd.DataFrame, n: int = charts.COTIZACIONES_A_MOSTRAR, con_titulo: bool = True) -> Figure:
    """Barras de las últimas n ruedas: el máximo en rojo, el mínimo en verde, con la variación diaria."""
    ultimos = data.tail(n).reset_index(drop=True)
    valores = ultimos["riesgo_pais"]
    maximo, minimo = valores.max(), valores.min()
    # Contra la rueda anterior real: la primera barra compara con el día previo a la ventana
    variaciones = (data["riesgo_pais"].pct_change() * 100).tail(n).tolist()

    fig, ax = _figura(10, 5.6, f"Riesgo país, últimas {len(ultimos)} ruedas" if con_titulo else None,
                      "Puntos básicos sobre los bonos del Tesoro de EE. UU. Más bajo es mejor." if con_titulo else None, leyenda=False)
    ax = ax if not hasattr(ax, "__len__") else ax[0]
    colores = [MALO if v == maximo else BUENO if v == minimo else CIAN for v in valores]
    ax.bar(ultimos.index, valores, width=0.68, color=colores, linewidth=0, zorder=3)
    for i, (valor, var) in enumerate(zip(valores, variaciones)):
        destacado = valor in (maximo, minimo)
        color = MALO if valor == maximo else BUENO if valor == minimo else TINTA
        ax.annotate(es(valor), (i, valor), xytext=(0, 14), textcoords="offset points", ha="center", va="bottom",
                    fontproperties=_fuente("semibold" if destacado else "normal", 9.5 if destacado else 8.5), color=color)
        if pd.notna(var):
            texto, color_var = _flecha(var)
            ax.annotate(texto, (i, valor), xytext=(0, 3), textcoords="offset points", ha="center", va="bottom",
                        fontproperties=_fuente("semibold", 6.8), color=color_var)
    _eje_ruedas(ax, ultimos["Fecha"].tolist(), cada=2)
    ax.set_xlim(-0.7, len(ultimos) - 0.3)
    ax.set_ylim(0, maximo * 1.2)
    paso, _ = charts._step_riesgo_pais(maximo)
    ax.yaxis.set_major_locator(MultipleLocator(paso))
    ax.yaxis.set_major_formatter(_formato_es())
    ax.set_axisbelow(True)
    return fig


# ── Inflación ────────────────────────────────────────────────────────────────

def inflacion(datos: pd.DataFrame, con_titulo: bool = True) -> Figure:
    """Inflación mensual en barras e interanual en línea, en dos ejes. `datos` es charts.preparar_inflacion."""
    n = len(datos)
    fig, ax = _figura(10, 6.4, f"Inflación de los últimos {n} meses" if con_titulo else None,
                      "Barras: variación mensual (eje izquierdo). Línea: variación de los últimos 12 meses (eje derecho)." if con_titulo else None,
                      margen_derecho=0.10)
    ax = ax if not hasattr(ax, "__len__") else ax[0]
    ax2 = ax.twinx()
    mensual, anual = datos["Inflación Mensual"], datos["Inflación Anual"]
    pos = list(range(n))
    ax.bar(pos, mensual, width=0.62, color=CIAN, alpha=0.9, linewidth=0, zorder=3, label="Inflación mensual")
    ax2.plot(pos, anual, color=VIOLETA, linewidth=2.8, marker="o", markersize=6, zorder=4, label="Inflación interanual")
    ax2.set_zorder(ax.get_zorder() + 1)
    ax2.patch.set_visible(False)
    ax.set_axisbelow(True)

    maximo = mensual.max()
    for i, v in enumerate(mensual):
        ax.annotate(f"{es(v, 1)}%", (i, v), xytext=(0, 5), textcoords="offset points", ha="center", va="bottom",
                    fontproperties=_fuente("semibold" if v == maximo else "normal", 10 if v == maximo else 9),
                    color=TINTA)
    bajo = alto = None
    if anual.notna().any():
        ultimo = anual.dropna().index[-1]
        ax2.annotate(f"{es(anual[ultimo], 1)}%", (ultimo, anual[ultimo]), xytext=(0, 11), textcoords="offset points",
                     ha="center", fontproperties=_fuente("semibold", 10), color=TINTA, bbox=_caja(VIOLETA))
        bajo, alto = anual.min(), anual.max()
        rango = (alto - bajo) or 1
        # La línea ocupa la franja de arriba y las barras la de abajo, así no se pisan
        ax2.set_ylim(bajo - rango * 2.6, alto + rango * 0.6)
    ax.set_ylim(0, maximo * 1.95)
    ax.set_xlim(-0.6, n - 0.4)
    ax.set_xticks(pos, [str(f).replace("/", "\n") for f in datos["Fecha"]])
    ax.tick_params(axis="x", labelsize=8.5)
    ax.grid(axis="x", visible=False)
    # Solo los rótulos que caen dentro de lo que cada eje muestra: el resto del rango es aire para separar las dos capas
    ax.yaxis.set_major_locator(MultipleLocator(1))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{es(v, 1)}%" if v <= maximo * 1.1 else ""))
    if bajo is not None:
        ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{es(v, 0)}%" if bajo - rango * 0.3 <= v <= alto + rango * 0.3 else ""))
    ax2.grid(False)
    ax2.spines["right"].set_visible(False)
    ax2.tick_params(axis="y", colors=VIOLETA, length=0)
    ax.tick_params(axis="y", colors=CIAN)
    for axis in (ax, ax2):
        axis.spines["left"].set_visible(False)
        axis.spines["bottom"].set_visible(False)
    manijas = ax.get_legend_handles_labels()[0] + ax2.get_legend_handles_labels()[0]
    rotulos = ax.get_legend_handles_labels()[1] + ax2.get_legend_handles_labels()[1]
    ax.legend(manijas, rotulos, loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, prop=_fuente("normal", 9.5), borderaxespad=0.2)
    return fig


# ── Variaciones acumuladas ───────────────────────────────────────────────────

def variaciones(va: pd.DataFrame, con_titulo: bool = True) -> Figure:
    """Solidario, blue e inflación acumulados. `va` es charts.preparar_variaciones."""
    inicio = pd.Timestamp(charts.FECHA_INICIO_VARIACIONES)
    fig, ax = _figura(10, 5.8, f"Dólar contra inflación desde {charts.mes_abreviado(inicio)}/{inicio:%Y}" if con_titulo else None,
                      "Variación acumulada de cada uno desde el inicio del período, en %." if con_titulo else None,
                      margen_derecho=0.13)
    ax = ax if not hasattr(ax, "__len__") else ax[0]
    columnas = [("Variación Solidario Acumulada", "Solidario", VERDE_AZULADO, "default"),
                ("Variación TCV Blue Acumulada", "Blue", CIAN, "default"),
                ("Inflación Mensual Acumulada", "Inflación", OLIVA, "steps-pre")]
    finales = []
    va = va.copy()
    # La inflación es mensual y las cotizaciones diarias: el escalón se completa hacia adelante
    va["Inflación Mensual Acumulada"] = va["Inflación Mensual Acumulada"].ffill()
    for col, rotulo, color, trazo in columnas:
        serie = va.dropna(subset=[col])
        ax.plot(serie["Fecha"], serie[col], color=color, linewidth=2.6, drawstyle=trazo, label=rotulo, solid_capstyle="round")
        if not serie.empty:
            finales.append((serie[col].iloc[-1], f"{es(serie[col].iloc[-1], 1)}%", color))
    ax.set_xlim(va["Fecha"].min(), va["Fecha"].max())
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2 if len(va) > 200 else 1))
    ax.xaxis.set_major_formatter(charts._formato_mes("%b/%y"))
    ax.yaxis.set_major_formatter(_formato_es(0, "%"))
    ax.grid(axis="x", visible=False)
    _leyenda(ax, ncol=3)
    ax.margins(y=0.12)
    _etiquetas_finales(ax, va["Fecha"].max(), finales)
    return fig


# ── Agregados monetarios ─────────────────────────────────────────────────────

def agregados(niveles: pd.DataFrame, interanual: pd.DataFrame, con_titulo: bool = True, tamano: tuple[float, float] = (10, 9.6)) -> Figure:
    """Niveles de base, circulación y M2, y su variación interanual contra la inflación."""
    fig, ax = _figura(*tamano, "Agregados monetarios" if con_titulo else None,
                      "Últimos 12 meses. Arriba, cuánto hay en circulación; abajo, cuánto creció contra la inflación." if con_titulo else None,
                      paneles=2, margen_derecho=0.12)
    colores = {"Base monetaria": CIAN, "Circulación monetaria": VIOLETA, "M2": OLIVA}
    _subtitulo(ax[0], "Niveles, en billones de pesos")
    finales = []
    for rotulo, datos in niveles.groupby("serie", sort=False):
        ax[0].plot(datos["Fecha"], datos["billones"], color=colores[rotulo], linewidth=2.4, label=rotulo)
        finales.append((datos["billones"].iloc[-1], es(datos["billones"].iloc[-1], 1), colores[rotulo]))
    ax[0].margins(y=0.15)
    _etiquetas_finales(ax[0], niveles["Fecha"].max(), finales)
    ax[0].yaxis.set_major_formatter(_formato_es())

    colores_ia = {"Base monetaria": CIAN, "M2": OLIVA, "M3 (mensual)": AZUL, "Inflación interanual": TINTA}
    _subtitulo(ax[1], "Variación interanual contra la inflación")
    finales = []
    for rotulo, datos in interanual.groupby("serie", sort=False):
        color = colores_ia[rotulo]
        if rotulo == "Inflación interanual":
            # Fechada a fin de mes, cubre ese mes: el escalón va hacia atrás
            ax[1].plot(datos["Fecha"], datos["interanual"], color=color, linewidth=2.2, linestyle="--", drawstyle="steps-pre", label=rotulo)
        elif rotulo == "M3 (mensual)":
            ax[1].plot(datos["Fecha"], datos["interanual"], color=color, linestyle="none", marker="D", markersize=6, label=rotulo)
        else:
            ax[1].plot(datos["Fecha"], datos["interanual"], color=color, linewidth=2.4, label=rotulo)
        finales.append((datos["interanual"].iloc[-1], f"{es(datos['interanual'].iloc[-1], 0)}%", color))
    ax[1].axhline(0, color=SECUNDARIO, linewidth=0.8, alpha=0.6)
    ax[1].margins(y=0.15)
    _etiquetas_finales(ax[1], interanual["Fecha"].max(), finales)
    ax[1].yaxis.set_major_formatter(_formato_es(0, "%"))

    for axis in ax:
        axis.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        axis.xaxis.set_major_formatter(charts._formato_mes("%b/%y"))
        axis.set_xlim(niveles["Fecha"].min() - pd.Timedelta(days=6), niveles["Fecha"].max())
        axis.grid(axis="x", visible=False)
        _leyenda(axis, ncol=4)
    return fig


# ── Deuda en dólares ─────────────────────────────────────────────────────────

def _sin_datos(ax, texto: str) -> None:
    ax.text(0.5, 0.5, texto, transform=ax.transAxes, ha="center", va="center", fontproperties=_fuente("normal", 11), color=TENUE)
    ax.set_xticks([])
    ax.set_yticks([])
    ax.grid(False)


def deuda(datos: dict, con_titulo: bool = True, tamano: tuple[float, float] = (10, 11.6)) -> Figure:
    """Deuda bruta del Tesoro, préstamos al sector privado y deuda del BCRA, todo en dólares."""
    fig, ax = _figura(*tamano, "Endeudamiento, en dólares" if con_titulo else None,
                      "Miles de millones de USD. Lo que viene en pesos se convierte con el mayorista de cada día." if con_titulo else None,
                      paneles=3, margen_derecho=0.12)
    # 1. Deuda bruta del Tesoro
    _subtitulo(ax[0], "Deuda bruta del Tesoro nacional, a fin de cada mes")
    tesoro = datos.get("tesoro")
    if tesoro is None or tesoro.empty:
        _sin_datos(ax[0], "Sin datos de la Secretaría de Finanzas para este día")
    else:
        ax[0].plot(tesoro["Mes"], tesoro["miles_de_millones"], color=CIAN, linewidth=2.4, label="Deuda bruta")
        firmes, prov = tesoro[~tesoro["provisorio"]], tesoro[tesoro["provisorio"]]
        ax[0].plot(firmes["Mes"], firmes["miles_de_millones"], linestyle="none", marker="o", markersize=5.5, color=CIAN)
        if not prov.empty:
            ax[0].plot(prov["Mes"], prov["miles_de_millones"], linestyle="none", marker="o", markersize=9, markerfacecolor="none",
                       markeredgecolor=TINTA, markeredgewidth=2, label="Provisorio (puede corregirse)")
        ax[0].margins(y=0.2)
        _etiquetas_finales(ax[0], tesoro["Mes"].iloc[-1], [(tesoro["miles_de_millones"].iloc[-1], es(tesoro["miles_de_millones"].iloc[-1], 1), CIAN)])
        ax[0].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    # 2. Préstamos
    _subtitulo(ax[1], "Préstamos de los bancos a familias y empresas")
    prestamos = datos.get("prestamos")
    if prestamos is None:
        _sin_datos(ax[1], "Sin datos del BCRA para este día")
    else:
        ax[1].plot(prestamos["Fecha"], prestamos["miles_de_millones"], color=VIOLETA, linewidth=2.4, label="Préstamos al sector privado")
        ax[1].margins(y=0.2)
        _etiquetas_finales(ax[1], prestamos["Fecha"].iloc[-1], [(prestamos["miles_de_millones"].iloc[-1], es(prestamos["miles_de_millones"].iloc[-1], 1), VIOLETA)])
        ax[1].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    # 3. BCRA
    _subtitulo(ax[2], "Deuda del BCRA y adelantos al Tesoro")
    bcra = datos.get("bcra")
    if bcra is None:
        _sin_datos(ax[2], "Sin datos del BCRA para este día")
    else:
        colores = {charts.LETRAS: OLIVA, charts.ADELANTOS: AZUL}
        finales = []
        for rotulo, serie in bcra.groupby("serie", sort=False):
            ax[2].plot(serie["Fecha"], serie["miles_de_millones"], color=colores[rotulo], linewidth=2.4, label=rotulo.split(" (")[0])
            finales.append((serie["miles_de_millones"].iloc[-1], es(serie["miles_de_millones"].iloc[-1], 1), colores[rotulo]))
        ax[2].set_ylim(bottom=0)
        ax[2].margins(y=0.15)
        _etiquetas_finales(ax[2], bcra["Fecha"].max(), finales)
        ax[2].xaxis.set_major_locator(mdates.MonthLocator(interval=2))

    for axis, hay in zip(ax, [tesoro is not None and not tesoro.empty, prestamos is not None, bcra is not None]):
        if not hay:
            continue
        axis.xaxis.set_major_formatter(charts._formato_mes("%b/%y"))
        axis.yaxis.set_major_formatter(_formato_es())
        axis.margins(x=0.02)
        axis.grid(axis="x", visible=False)
        _leyenda(axis, ncol=2)
    return fig


# ── Salida ───────────────────────────────────────────────────────────────────

def png(fig: Figure) -> bytes:
    """La figura transparente en PNG a 200 dpi (el vidrio la espera así: 1 pulgada = 100 px lógicos)."""
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        fig.savefig(buffer, format="png", dpi=DPI, transparent=True)
    return buffer.getvalue()


# Cómo redibujar, para la presentación, los gráficos que ahí van como imagen (agregados y deuda): la versión sin título
# y de otro tamaño, porque en una diapositiva la letra tiene que verse. Lo registra charts al dibujar el del mail.
PARA_DIAPOSITIVA: dict[str, Callable[[], Figure]] = {}


def guardar(fig: Figure, nombre: str, carpeta: Path, diapositiva: Callable[[], Figure] | None = None) -> Path:
    """Guarda el gráfico montado sobre vidrio (el .jpg del mail) y registra, si hay, cómo redibujarlo para la presentación."""
    ruta = Path(carpeta) / nombre
    estilo.tarjeta_de_grafico(png(fig)).save(ruta, quality=90, optimize=True)
    if diapositiva is None:
        PARA_DIAPOSITIVA.pop(nombre, None)
    else:
        PARA_DIAPOSITIVA[nombre] = diapositiva
    log.info("Gráfico guardado: %s", ruta.name)
    return ruta


def png_para_diapositiva(nombre: str) -> bytes | None:
    """El PNG transparente de ese gráfico pensado para la presentación, o None si esta corrida no lo registró."""
    dibujar = PARA_DIAPOSITIVA.get(nombre)
    if dibujar is None:
        return None
    with estilo.contexto():
        return png(dibujar())
