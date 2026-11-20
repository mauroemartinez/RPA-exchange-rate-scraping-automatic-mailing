"""Presentación ejecutiva en PowerPoint: nueve diapositivas con lo que deja la corrida del día.

El armado visual (vidrio azul de GlobalAIze, gráficos nativos y todo el diseño) está en
reporte/marca/deck.py; este módulo conserva la puerta de entrada `armar`, los datos fijos (links,
fuentes, tecnologías), las frases calculadas con los datos del día y los metadatos del archivo.

Las nueve diapositivas:
1. Portada con el logo de GlobalAIze, los links del autor y las tecnologías del proyecto.
2. Tablero: blue, MEP, billete, riesgo país, BADLAR y el forward de Fisher.
3. Tipos de cambio: el análisis de IA del día y dos gráficos nativos, paralelas y oficiales.
4. Riesgo país: gráfico nativo, con el resumen del día y el comentario de Gemini.
5. Inflación y variaciones acumuladas, también nativos.
6 y 7. Agregados monetarios y deuda, con el resumen del día y lo ideal.
8. Bitcoin, con el gráfico de siempre.
9. Fuentes y contacto, como el pie del mail.

Cada gráfico lleva su frase: la de Gemini cuando la hay y, si no, un resumen calculado acá con los
datos del día. Los colores siguen el criterio del mail, mirado desde la macro: que el dólar o el
riesgo país bajen es una buena noticia (verde) y que suban, una mala (rojo), siempre con flecha.

La arma todos los días la etapa `presentacion` de pipeline.py, con los datos y los textos de esa
misma corrida, y queda en Previews/ con un nombre fijo (ARCHIVO), que git ignora: la etapa previews
la publica sola en la rama reporte-ejecutivo, que se reemplaza entera cada día. Para rearmarla a
mano desde Supabase está scripts/presentacion_ejecutiva.py.
"""

import logging
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
from pptx.opc.constants import RELATIONSHIP_TYPE

from reporte import charts, indicadores
from reporte.scrapers import ambito, bcra, bna, dolarhoy, fed, finanzas, riesgo_pais

log = logging.getLogger(__name__)

ARCHIVO = "Reporte Ejecutivo.pptx"

# Metadatos del archivo. La plantilla de python-pptx trae los de su autor
# (last_modified_by, un comentario y fechas de 2013): se reemplazan todos.
AUTOR = "Seguimiento Macroeconómico"

SIN_ANALISIS = "Sin análisis para este día."

RECURSOS = Path(__file__).resolve().parent / "recursos"
ALIAS = "mauroemartinezmp"
MAIL = "mauro@globalaize.com"

# (ícono, rótulo, link): los mismos del cierre del mail
LINKS = [
    ("linkedin.png", "LinkedIn", "https://linkedin.com/in/mauroemartinez/"),
    ("github.png", "GitHub", "https://github.com/mauroemartinez/"),
    ("globalaize.png", "GlobalAIze", "https://www.globalaize.com"),
    ("linkedin.png", "GlobalAIze en LinkedIn", "https://www.linkedin.com/company/globalaize"),
]

# Las tecnologías del pie de la portada: (archivo en recursos/tecnologias, rótulo)
TECNOLOGIAS = [
    ("python", "Python"), ("playwright", "Playwright"), ("pandas", "pandas"), ("pydantic", "Pydantic"),
    ("sqlalchemy", "SQLAlchemy"), ("postgresql", "PostgreSQL"), ("supabase", "Supabase"), ("gemini", "Gemini"),
    ("matplotlib", "Matplotlib"), ("seaborn", "seaborn"), ("jinja", "Jinja"), ("powerpoint", "PowerPoint"),
    ("githubactions", "GitHub Actions"), ("cloudflare", "Cloudflare"), ("pytest", "pytest"),
]

FUENTES = [
    ("Cotizaciones oficiales", bna.WEB_BNA),
    ("Cotizaciones paralelas", dolarhoy.WEB_DOLARHOY),
    ("Dólar MEP", ambito.WEB_MEP),
    ("Euro blue", ambito.WEB_EURO),
    ("Riesgo país y feriados", riesgo_pais.API_BASE),
    ("Tasa de la FED (EFFR)", fed.API_URL),
    ("BCRA: tasas, inflación, agregados, deuda y dólar mayorista", bcra.API_BASE),
    ("Deuda bruta del Tesoro (Secretaría de Finanzas)", finanzas.PAGINA),
    ("Bitcoin (Yahoo Finance)", "https://finance.yahoo.com/quote/BTC-USD"),
]


def _fecha(valor) -> date:
    """La Fecha de una fila: texto 'YYYY-MM-DD' en el histórico, date en la fila recién armada."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    return date.fromisoformat(str(valor)[:10])


def _num(valor: float, decimales: int = 2) -> str:
    return indicadores.numero(valor, decimales)


def _signo(valor: float, decimales: int = 2) -> str:
    return f"{'+' if valor >= 0 else '-'}{_num(abs(valor), decimales)}"


def _comentario(comentarios: dict, cid: str, palabra: str) -> str | None:
    """El comentario de Gemini de ese gráfico cuyo título menciona `palabra` (paralela, oficial, riesgo...)."""
    return next((texto for titulo, texto in comentarios.get(cid, []) if palabra in titulo.lower()), None)


def frase_paralelas(hoy, ayer) -> str:
    def dato(nombre, col):
        return f"{nombre} $ {_num(hoy[col])} ({_signo((hoy[col] / ayer[col] - 1) * 100)}%)"
    return (f"{dato('Blue', 'TCV_Blue')}, {dato('MEP', 'TCV_MEP')}, {dato('euro blue', 'TCV_Euro')} "
            f"y solidario $ {_num(hoy['Solidario'])}, siempre a la venta y contra la rueda anterior.")


def frase_oficiales(hoy, ayer) -> str:
    def dato(nombre, col):
        return f"{nombre} $ {_num(hoy[col])} ({_signo((hoy[col] / ayer[col] - 1) * 100)}%)"
    return (f"{dato('Billete BNA', 'TCV_Billete')} y {dato('divisas', 'TCV_Divisas')}, a la venta y contra la "
            "rueda anterior. El billete es el que compra la gente en el banco; divisas, el de las empresas.")


def frase_riesgo(df) -> str:
    ultimos = df["riesgo_pais"].head(charts.COTIZACIONES_A_MOSTRAR)
    hoy, ayer = df["riesgo_pais"].iloc[0], df["riesgo_pais"].iloc[1]
    return (f"{_num(hoy, 0)} puntos, {_signo(hoy - ayer, 0)} contra la rueda anterior. En las últimas "
            f"{len(ultimos)} ruedas estuvo entre {_num(ultimos.min(), 0)} y {_num(ultimos.max(), 0)}.\n"
            "Es lo que paga Argentina por encima de los bonos de Estados Unidos: cuanto más bajo, más barato le sale "
            "el crédito al país y a sus empresas.")


def frase_inflacion(inflacion: pd.DataFrame | None, df) -> str | None:
    """La última inflación mensual e interanual, y lo acumulado desde el inicio del gráfico de variaciones."""
    if inflacion is None or inflacion.empty:
        return None
    serie = inflacion.dropna(subset=["Inflación Mensual"])
    ultimo, previo = serie.iloc[-1], serie.iloc[-2] if len(serie) > 1 else None
    texto = f"La inflación de {indicadores.mes_y_anio(ultimo['Fecha'])} fue {_num(ultimo['Inflación Mensual'], 1)}%"
    if previo is not None:
        texto += f" ({indicadores.MESES[previo['Fecha'].month - 1]}: {_num(previo['Inflación Mensual'], 1)}%)"
    if pd.notna(ultimo.get("Inflación Anual")):
        texto += f" y la de los últimos 12 meses, {_num(ultimo['Inflación Anual'], 1)}%"
    texto += "."

    inicio = pd.Timestamp(charts.FECHA_INICIO_VARIACIONES)
    precios = ((serie[serie["Fecha"] >= inicio]["Inflación Mensual"] / 100 + 1).prod() - 1) * 100
    cotizaciones = df[["Fecha", "TCV_Blue", "Solidario"]].assign(Fecha=lambda d: pd.to_datetime(d["Fecha"].astype(str).str[:10]))
    antes = cotizaciones[cotizaciones["Fecha"] < inicio]
    if not antes.empty:
        base, hoy = antes.iloc[0], cotizaciones.iloc[0]
        blue = (hoy["TCV_Blue"] / base["TCV_Blue"] - 1) * 100
        solidario = (hoy["Solidario"] / base["Solidario"] - 1) * 100
        texto += (f"\nDesde {indicadores.mes_y_anio(inicio)}, los precios subieron {_num(precios, 1)}%, el dólar blue "
                  f"{_signo(blue, 1)}% y el solidario {_signo(solidario, 1)}%: el dólar "
                  f"{'subió menos que los precios, así que en pesos de hoy está más barato' if blue < precios else 'subió más que los precios, así que en pesos de hoy está más caro'}.")
    return texto


def frase_btc(btc: pd.DataFrame | None) -> str | None:
    if btc is None or btc.empty or "Close" not in btc:
        return None
    cierre = btc["Close"].dropna()
    if len(cierre) < 2:
        return None
    ultimo, fecha = float(cierre.iloc[-1]), cierre.index[-1]

    def cambio(dias: int) -> str | None:
        previos = cierre[cierre.index <= fecha - pd.Timedelta(days=dias)]
        if previos.empty and (fecha - cierre.index[0]).days >= dias - 10:
            previos = cierre.iloc[:1]  # la serie viene recortada a un año justo: su primer dato
        return None if previos.empty else f"{_signo((ultimo / float(previos.iloc[-1]) - 1) * 100, 1)}%"

    partes = [f"en {t} {c}" for t, c in (("7 días", cambio(7)), ("30 días", cambio(30)), ("el último año", cambio(365))) if c]
    texto = f"Bitcoin cerró en USD {_num(ultimo, 0)} el {fecha:%d/%m/%Y}"
    texto += (": " + ", ".join(partes) + ".") if partes else "."
    if "Volatility" in btc and pd.notna(btc["Volatility"].iloc[-1]):
        texto += f"\nVolatilidad diaria de las últimas 20 ruedas: {_num(float(btc['Volatility'].iloc[-1]), 1)}%."
    return texto


def _metadatos(prs, fecha: date) -> None:
    propiedades = prs.core_properties
    propiedades.title = f"Reporte Macroeconómico {fecha:%d/%m/%Y}"
    propiedades.author = AUTOR
    propiedades.last_modified_by = AUTOR
    propiedades.comments = ""
    propiedades.revision = 1
    # python-pptx escribe estas fechas como UTC
    ahora = datetime.now(UTC).replace(tzinfo=None, microsecond=0)
    propiedades.created = ahora
    propiedades.modified = ahora


def _colores_de_link(prs) -> None:
    """Los links en el cian y el violeta de GlobalAIze: PowerPoint ignora el color del texto y usa el del tema."""
    import re

    tema = prs.slide_masters[0].part.part_related_by(RELATIONSHIP_TYPE.THEME)
    xml = tema.blob.decode("utf-8")
    for etiqueta, color in (("hlink", "0DA4CF"), ("folHlink", "795EC9")):
        xml = re.sub(rf"(<a:{etiqueta}>\s*<a:srgbClr val=\")[0-9A-Fa-f]{{6}}", rf"\g<1>{color}", xml)
    tema._blob = xml.encode("utf-8")


def _propiedades_de_aplicacion(prs) -> None:
    """docProps/app.xml con los datos de este archivo.

    La plantilla de python-pptx trae los de la PowerPoint en que se armó (Microsoft
    Macintosh PowerPoint 14, presentación 4:3, cero diapositivas). python-pptx no
    tiene API para esta parte, así que se reescribe entera; es un XML de propiedades
    opcionales y PowerPoint lo acepta así de corto.
    """
    parte = prs.part.package.part_related_by(RELATIONSHIP_TYPE.EXTENDED_PROPERTIES)
    parte._blob = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        f"<Application>{AUTOR}</Application>"
        "<PresentationFormat>16:9</PresentationFormat>"
        f"<Slides>{len(prs.slides)}</Slides>"
        "</Properties>"
    ).encode()


def armar(df, imagenes, salida, parrafo=None, comentarios=None, explicaciones=None, inflacion=None, btc=None):
    """Arma la presentación en `salida`/ARCHIVO y devuelve su ruta (ver reporte/marca/deck.py)."""
    from reporte.marca import deck

    return deck.armar(df, imagenes, salida, parrafo, comentarios, explicaciones, inflacion, btc)
