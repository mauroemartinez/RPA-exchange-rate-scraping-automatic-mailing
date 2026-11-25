"""Tablero de seguimiento macroeconómico, con la marca de GlobalAIze, en castellano e inglés.

Lee dos archivos que sube el workflow datos-dashboard.yml una vez por día hábil, después
de la corrida diaria, ambos desde el 1 de enero de hace dos años (la base completa no se
publica):
- dashboard/data/mercado.csv: dólares, riesgo país, tasas y los análisis de IA.
- dashboard/data/series.csv: inflación, agregados monetarios, letras del BCRA, deuda del
  Tesoro, mayorista y bitcoin.
Con DASHBOARD_CSV (variable de entorno) se puede pasar otro mercado.csv, por ejemplo el
adjunto del mail.

El tablero no necesita credenciales y no dice dónde están los datos.

Uso:
    pip install -r dashboard/requirements.txt
    streamlit run dashboard/app.py
"""

import base64
import html
import os
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as componentes
from plotly.offline import get_plotlyjs_version

AQUI = Path(__file__).resolve().parent
DATOS = AQUI / "data"
REPO = "https://github.com/mauroemartinez/RPA-exchange-rate-scraping-automatic-mailing"

st.set_page_config(
    page_title="Seguimiento macroeconómico | GlobalAIze",
    page_icon=str(AQUI / "assets" / "globalaize-favicon.svg"),
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Idioma ────────────────────────────────────────────────────────────────────
IDIOMA = "en" if st.query_params.get("lang") == "en" else "es"

TEXTOS = {
    "es": {
        "titulo": "Seguimiento macroeconómico de Argentina", "oscuro": "Oscuro", "claro": "Claro",
        "bajada": "Dólares, brechas, riesgo país, tasas, inflación, dinero, deuda y bitcoin, todos los días hábiles. "
                  "Último dato: <b>{fecha}</b>. Datos publicados desde el {desde}.",
        "blue": "Dólar blue (venta)", "mep": "Dólar MEP", "oficial": "Oficial BNA (venta)",
        "brecha": "Brecha blue vs. oficial", "riesgo": "Riesgo país", "badlar": "BADLAR (TEA)",
        "inflacion": "Inflación mensual", "bitcoin": "Bitcoin",
        "vs": "vs. {fecha}", "30d": "en 30 días", "anio": "en el año", "mes_ant": "vs. {mes}", "12m": "interanual {pct}",
        "nota_tarjetas": "Variaciones contra el día hábil anterior ({ayer}), contra 30 días atrás y contra el cierre del año "
                         "pasado (31/12/{anio}). Rojo es una suba de algo que conviene que baje (dólares, brecha, riesgo "
                         "país, inflación) y verde, una baja; en tasas y bitcoin la flecha solo dice si subió o bajó. "
                         "\"pp\" son puntos porcentuales.",
        "periodo": "Período de los gráficos",
        "p1m": "1 mes", "p3m": "3 meses", "p6m": "6 meses", "p1a": "1 año", "pytd": "En el año", "ptodo": "Desde {desde}",
        "pest": ["Oficiales", "Paralelos", "Brechas", "Riesgo país", "Tasas", "Inflación", "Dinero y BCRA", "Deuda",
                 "Bitcoin", "Análisis de IA", "Datos", "Fuentes"],
        "sel_oficiales": "Cotizaciones oficiales", "sel_paralelos": "Cotizaciones paralelas", "sel_brechas": "Brechas",
        "sel_dinero": "Series", "elegi": "Elegí al menos una serie.",
        "en_periodo": "{serie}, en el período: mínimo {min} ({fmin}), máximo {max} ({fmax}).",
        "nota_brechas": "Cuánto más caro está el primero que el segundo, en porcentaje. Negativo quiere decir que está más barato.",
        "nota_tasas": "Tasas anuales efectivas. El diferencial, en puntos porcentuales, es cuánto más paga un plazo fijo "
                      "en pesos que la tasa de referencia de EE. UU., antes de descontar la devaluación.",
        "nota_mensual": "Datos mensuales: con períodos cortos se muestran los últimos 12 meses.",
        "nota_inflacion": "Inflación mensual (barras) e interanual (línea), en porcentaje.",
        "nota_dinero": "En billones de pesos (millones de millones). Fuente: BCRA.",
        "nota_deuda": "Deuda bruta de la Administración Central, en miles de millones de dólares, al cierre de cada mes. "
                      "Los últimos meses pueden ser provisorios.",
        "nota_ia": "Escritos por IA sobre las cifras que calcula el pipeline: la IA comenta los números, no los inventa.",
        "sin_ia": "No hay análisis de IA en el período.",
        "ia_idioma": "",
        "descargar": "Descargar CSV del período",
        "nota_datos": "Las últimas 30 ruedas; la descarga trae todo el período elegido. Los datos publicados empiezan el {desde}.",
        "fuente": "Fuente", "aporta": "Qué aporta",
        "nota_fuentes": "Cada valor se guarda con la fecha y la unidad de su fuente. Cómo se consigue y se valida cada serie "
                        "está en el <a href=\"{repo}\" target=\"_blank\">repositorio</a>.",
        "pie": "Globalizate con <a href=\"https://www.globalaize.com\" target=\"_blank\">GlobalAIze</a>. "
               "Código abierto en <a href=\"{repo}\" target=\"_blank\">GitHub</a>.",
        "sin_datos": "No hay datos para mostrar.",
        "min": "mín.", "max": "máx.",
        "billones": "billones de $", "usd_bn": "miles de millones de USD",
        "meses": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
    },
    "en": {
        "titulo": "Argentina's macroeconomy, day by day", "oscuro": "Dark", "claro": "Light",
        "bajada": "Dollar rates, gaps, country risk, interest rates, inflation, money, debt and bitcoin, every business day. "
                  "Latest data: <b>{fecha}</b>. Data published from {desde}.",
        "blue": "Blue dollar (sell)", "mep": "MEP dollar", "oficial": "Official BNA (sell)",
        "brecha": "Blue vs. official gap", "riesgo": "Country risk", "badlar": "BADLAR (APY)",
        "inflacion": "Monthly inflation", "bitcoin": "Bitcoin",
        "vs": "vs. {fecha}", "30d": "in 30 days", "anio": "year to date", "mes_ant": "vs. {mes}", "12m": "year on year {pct}",
        "nota_tarjetas": "Changes against the previous business day ({ayer}), 30 days ago and last year's close "
                         "(12/31/{anio}). Red is a rise in something that should go down (dollars, gap, country risk, "
                         "inflation) and green a fall; for rates and bitcoin the arrow only says up or down. "
                         "\"pp\" are percentage points.",
        "periodo": "Chart period",
        "p1m": "1 month", "p3m": "3 months", "p6m": "6 months", "p1a": "1 year", "pytd": "Year to date", "ptodo": "Since {desde}",
        "pest": ["Official", "Parallel", "Gaps", "Country risk", "Rates", "Inflation", "Money & central bank", "Debt",
                 "Bitcoin", "AI analysis", "Data", "Sources"],
        "sel_oficiales": "Official rates", "sel_paralelos": "Parallel rates", "sel_brechas": "Gaps",
        "sel_dinero": "Series", "elegi": "Pick at least one series.",
        "en_periodo": "{serie}, in the period: low {min} ({fmin}), high {max} ({fmax}).",
        "nota_brechas": "How much more expensive the first one is than the second, in percent. Negative means cheaper.",
        "nota_tasas": "Annual effective rates. The spread, in percentage points, is how much more a peso fixed-term deposit "
                      "pays than the US benchmark rate, before the devaluation.",
        "nota_mensual": "Monthly data: short periods show the last 12 months.",
        "nota_inflacion": "Monthly inflation (bars) and year-on-year inflation (line), in percent.",
        "nota_dinero": "In ARS trillions. Source: Argentina's central bank (BCRA).",
        "nota_deuda": "Central Government gross debt, in USD billions, at the end of each month. The latest months may be "
                      "provisional.",
        "nota_ia": "Written by AI on the figures the pipeline calculates: the AI comments on the numbers, it does not make them up.",
        "sin_ia": "No AI analysis in this period.",
        "ia_idioma": "The analyses are written in Spanish.",
        "descargar": "Download the period as CSV",
        "nota_datos": "The latest 30 trading days; the download has the whole chosen period. Published data starts on {desde}.",
        "fuente": "Source", "aporta": "What it provides",
        "nota_fuentes": "Every value is stored with its source's date and unit. How each series is collected and validated "
                        "is explained in the <a href=\"{repo}\" target=\"_blank\">repository</a>.",
        "pie": "Go global with <a href=\"https://www.globalaize.com/en/\" target=\"_blank\">GlobalAIze</a>. "
               "Open source on <a href=\"{repo}\" target=\"_blank\">GitHub</a>.",
        "sin_datos": "No data to show.",
        "min": "low", "max": "high",
        "billones": "ARS trillion", "usd_bn": "USD billion",
        "meses": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    },
}
T = TEXTOS[IDIOMA]

NOMBRES = {
    "es": {
        "TCV_Billete": "Billete BNA (venta)", "TCC_Billete": "Billete BNA (compra)", "TCV_Divisas": "Divisas BNA (venta)",
        "TCC_Divisas": "Divisas BNA (compra)", "Solidario": "Solidario", "tipo_cambio_mayorista": "Mayorista (A3500)",
        "TCV_Blue": "Blue (venta)", "TCC_Blue": "Blue (compra)", "TCV_MEP": "MEP", "TCV_Euro": "Euro blue (venta)",
        "TCC_Euro": "Euro blue (compra)",
        "g_blue_of": "Blue vs. oficial BNA", "g_mep_div": "MEP vs. divisas BNA", "g_blue_mep": "Blue vs. MEP",
        "g_sol_blue": "Solidario vs. blue", "g_of_may": "Oficial BNA vs. mayorista",
        "riesgo_pais": "Riesgo país", "bcra_tea": "BADLAR (TEA)", "fed_tea": "FED (EFFR)", "dif": "Diferencial BADLAR − FED",
        "inflacion_mensual": "Inflación mensual", "inflacion_interanual": "Inflación interanual",
        "base_monetaria": "Base monetaria", "circulacion_monetaria": "Circulación monetaria",
        "billetes_publico": "Billetes en poder del público", "m2": "M2", "m2_transaccional_privado": "M2 privado transaccional",
        "prestamos_sector_privado": "Préstamos al sector privado", "letras_bcra_pesos": "Letras del BCRA en pesos",
        "letras_bcra_moneda_extranjera": "Letras del BCRA en moneda extranjera", "adelantos_transitorios": "Adelantos transitorios al Tesoro",
        "deuda_bruta_tesoro": "Deuda bruta del Tesoro", "bitcoin": "Bitcoin (USD)",
    },
    "en": {
        "TCV_Billete": "BNA cash (sell)", "TCC_Billete": "BNA cash (buy)", "TCV_Divisas": "BNA wire (sell)",
        "TCC_Divisas": "BNA wire (buy)", "Solidario": "Solidarity (with taxes)", "tipo_cambio_mayorista": "Wholesale (A3500)",
        "TCV_Blue": "Blue (sell)", "TCC_Blue": "Blue (buy)", "TCV_MEP": "MEP", "TCV_Euro": "Blue euro (sell)",
        "TCC_Euro": "Blue euro (buy)",
        "g_blue_of": "Blue vs. BNA official", "g_mep_div": "MEP vs. BNA wire", "g_blue_mep": "Blue vs. MEP",
        "g_sol_blue": "Solidarity vs. blue", "g_of_may": "BNA official vs. wholesale",
        "riesgo_pais": "Country risk", "bcra_tea": "BADLAR (APY)", "fed_tea": "FED (EFFR)", "dif": "BADLAR − FED spread",
        "inflacion_mensual": "Monthly inflation", "inflacion_interanual": "Year-on-year inflation",
        "base_monetaria": "Monetary base", "circulacion_monetaria": "Currency in circulation",
        "billetes_publico": "Cash held by the public", "m2": "M2", "m2_transaccional_privado": "Private transactional M2",
        "prestamos_sector_privado": "Loans to the private sector", "letras_bcra_pesos": "BCRA peso bills",
        "letras_bcra_moneda_extranjera": "BCRA foreign currency bills", "adelantos_transitorios": "Temporary advances to the Treasury",
        "deuda_bruta_tesoro": "Treasury gross debt", "bitcoin": "Bitcoin (USD)",
    },
}
N = NOMBRES[IDIOMA]

FUENTES = {
    "es": [
        ("Banco Nación", "Dólar minorista billete y divisa, compra y venta; el solidario se calcula sobre el billete"),
        ("DolarHoy", "Dólar paralelo (blue), compra y venta"),
        ("Ámbito", "Dólar MEP y euro blue"),
        ("ArgentinaDatos", "Riesgo país, con su fecha de publicación"),
        ("API de estadísticas del BCRA", "Tasa BADLAR, inflación, agregados monetarios, letras, adelantos transitorios, "
                                         "préstamos al sector privado y mayorista A3500"),
        ("St. Louis FRED", "Tasa efectiva de los fondos federales de EE. UU. (si FRED falla, la de la Fed de Nueva York)"),
        ("Secretaría de Finanzas", "Deuda bruta del Tesoro, mes a mes"),
        ("Yahoo Finance", "Bitcoin en dólares"),
        ("Google Gemini", "Los análisis de IA, sobre las cifras que calcula el pipeline"),
    ],
    "en": [
        ("Banco Nación", "Retail cash and wire dollar, buy and sell; the solidarity rate is computed on the cash rate"),
        ("DolarHoy", "Parallel (blue) dollar, buy and sell"),
        ("Ámbito", "MEP dollar and blue euro"),
        ("ArgentinaDatos", "Country risk, with its publication date"),
        ("BCRA statistics API", "BADLAR rate, inflation, monetary aggregates, bills, temporary advances, private sector "
                                "loans and the A3500 wholesale rate"),
        ("St. Louis FRED", "US effective federal funds rate (if FRED fails, from the New York Fed)"),
        ("Secretaría de Finanzas", "Treasury gross debt, month by month"),
        ("Yahoo Finance", "Bitcoin in US dollars"),
        ("Google Gemini", "The AI analyses, on the figures the pipeline calculates"),
    ],
}

# ── Modo claro u oscuro: arranca con el del sistema y se cambia con el botón Oscuro / Claro ──
# (?tema=claro u ?tema=oscuro). Los colores de los controles de Streamlit se pisan con
# CSS, así que todo cambia junto aunque el sistema esté en el otro modo.
if st.query_params.get("tema") in ("claro", "oscuro"):
    OSCURO = st.query_params["tema"] == "oscuro"
else:
    try:
        OSCURO = (st.context.theme.type or "dark") != "light"
    except Exception:
        OSCURO = True

if OSCURO:
    C = dict(
        papel="#040F23", tinta="#F0EEE9", secundario="#BBC5D1", tenue="#8D9AA8", eje="#8D9AA8",
        grilla="rgba(255,255,255,0.08)", vidrio="rgb(5 30 69 / .70)", borde="rgb(235 245 255 / .12)",
        canto="rgb(235 245 255 / .34)", sombra="0 8px 24px rgb(1 6 16 / .45)", acento="#1FB5E3",
        sube="#62D286", baja="#EF6661", hover="#051E45", linea_tabs="#2A394D",
        luces="radial-gradient(40% 55% at 20% 38%, rgb(34 181 225 / .17), transparent 70%),"
              "radial-gradient(40% 55% at 82% 78%, rgb(31 79 168 / .20), transparent 70%),"
              "radial-gradient(45% 35% at 52% 10%, rgb(16 52 140 / .20), transparent 70%), #040F23",
        series=["#0DA4CF", "#795EC9", "#A69722", "#4170CB", "#C13234", "#3BAB8D", "#B33879", "#47AB4F"],
        logo="globalaize-logo-horizontal-{idioma}-dark.svg",
    )
else:
    C = dict(
        papel="#F3F1EC", tinta="#051E45", secundario="#3E4E66", tenue="#6B7A8E", eje="#6B7A8E",
        grilla="rgba(5,30,69,0.08)", vidrio="rgb(255 255 255 / .78)", borde="rgb(5 30 69 / .10)",
        canto="rgb(255 255 255 / .95)", sombra="0 8px 24px rgb(5 30 69 / .10)", acento="#1687A9",
        sube="#299236", baja="#B00A1D", hover="#FFFFFF", linea_tabs="#D3DAE4",
        luces="radial-gradient(40% 55% at 20% 38%, rgb(34 181 225 / .10), transparent 70%),"
              "radial-gradient(40% 55% at 82% 78%, rgb(31 79 168 / .09), transparent 70%), #F3F1EC",
        series=["#1687A9", "#5933AB", "#A3940F", "#1B4BA9", "#B00A1D", "#199C7E", "#A51069", "#299236"],
        logo="globalaize-logo-horizontal-{idioma}.svg",
    )


BANDERAS = {
    "es": '<svg viewBox="0 0 30 20" aria-hidden="true"><rect width="30" height="20" fill="#74ACDF"/>'
          '<rect y="6.67" width="30" height="6.66" fill="#fff"/><circle cx="15" cy="10" r="2.2" fill="#F6B40E"/></svg>',
    "en": '<svg viewBox="0 0 30 20" aria-hidden="true"><rect width="30" height="20" fill="#B22234"/>'
          + "".join(f'<rect y="{i * 20 / 13 * 2 + 20 / 13:.3f}" width="30" height="{20 / 13:.3f}" fill="#fff"/>' for i in range(6))
          + '<rect width="12" height="10.77" fill="#3C3B6E"/></svg>',
}


def _logo() -> str:
    archivo = AQUI / "assets" / C["logo"].format(idioma=IDIOMA)
    return base64.b64encode(archivo.read_bytes()).decode()


def _estilos() -> None:
    css = """
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap" rel="stylesheet">
<style>
  .stApp { background: @luces; color: @tinta; }
  html, body, [class*="st-"], .stMarkdown, .stTabs, button, input, label {
    font-family: "IBM Plex Sans", system-ui, "Segoe UI", sans-serif;
  }
  [data-testid="stIconMaterial"] { font-family: "Material Symbols Rounded" !important; }
  .titulo { font-family: "Newsreader", Georgia, serif !important; font-weight: 500 !important; }
  /* Controles de Streamlit con los colores del tema elegido (pueden diferir del sistema) */
  [data-testid="stWidgetLabel"] p, .stMarkdown, .stMarkdown p, [data-testid="stMarkdownContainer"] { color: @tinta; }
  [data-testid="stButtonGroup"] button { background: @vidrio !important; color: @tinta !important; border-color: @borde !important; }
  [data-testid="stButtonGroup"] button[aria-checked="true"] { color: @acento !important; border-color: @acento !important; }
  [data-testid="stButtonGroup"] button p { color: inherit; }
  [data-testid="stMultiSelect"] div[role="group"] { background: @vidrio !important; border-color: @borde !important; color: @tinta !important; }
  [data-testid="stMultiSelect"] svg { color: @secundario !important; }
  [role="listbox"], [role="listbox"] [role="option"] { background: @hover !important; color: @tinta !important; }
  [data-testid="stAlert"] > div { background: @vidrio; color: @tinta; }
  [data-testid="stDownloadButton"] button { background: @vidrio; color: @tinta; border-color: @borde; }
  header[data-testid="stHeader"] { background: transparent; }
  [data-testid="stDecoration"], footer { display: none; }
  .block-container { padding-top: 2.2rem; max-width: 1400px; }
  .encabezado { display: flex; align-items: center; gap: 20px; }
  .encabezado img { height: 52px; width: auto; display: block; }
  .encabezado .titulo { font-size: 2.2rem; color: @tinta; line-height: 1.05; margin: 0; }
  @media (max-width: 900px) { .encabezado { flex-wrap: wrap; } .encabezado .titulo { font-size: 1.7rem; } }
  .idiomas { display: inline-flex; border: 1px solid @borde; border-radius: 8px; overflow: hidden; background: @vidrio; }
  .idiomas a { display: inline-flex; align-items: center; gap: 7px; padding: 6px 12px; color: @tinta !important;
               text-decoration: none !important; font-size: 0.9rem; border: 1px solid transparent; }
  .idiomas a + a { border-left-color: @borde; }
  .idiomas a.activo { color: @acento !important; border-color: @acento; border-radius: 8px; }
  .idiomas svg { width: 20px; height: 14px; border-radius: 2px; box-shadow: 0 0 0 1px rgb(0 0 0 / .15); flex: none; }
  .bajada { color: @secundario; font-size: 0.92rem; margin: 10px 0 14px; }
  /* Vidrio de la marca: tinte, desenfoque, canto de luz fino (más claro arriba a la izquierda
     y abajo a la derecha), sin brillo, sombra suave y radio 14. */
  .vidrio {
    position: relative; background: @vidrio;
    -webkit-backdrop-filter: blur(36px) saturate(120%); backdrop-filter: blur(36px) saturate(120%);
    border: 1.5px solid @borde; border-radius: 14px; box-shadow: @sombra;
  }
  .vidrio::before {
    content: ""; position: absolute; inset: -1.5px; border-radius: 14px; padding: 1.5px; pointer-events: none;
    background: linear-gradient(135deg, @canto, transparent 28%, transparent 72%, @canto);
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor; mask-composite: exclude;
  }
  .tarjetas { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin: 8px 0 8px; }
  .tarjeta { padding: 14px 16px; }
  .tarjeta .rotulo { color: @secundario; font-size: 0.76rem; letter-spacing: .04em; text-transform: uppercase; font-weight: 600; }
  .tarjeta .valor { color: @tinta; font-size: 1.65rem; font-weight: 600; margin: 2px 0 6px; }
  .tarjeta .delta { font-size: 0.8rem; color: @secundario; line-height: 1.55; }
  .tarjeta .delta b { font-weight: 600; }
  .sube { color: @sube; } .baja { color: @baja; } .neutro { color: @tinta; }
  .stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid @linea_tabs; flex-wrap: wrap; }
  .stTabs [data-baseweb="tab"] { color: @secundario; font-weight: 500; padding: 8px 12px; }
  .stTabs [aria-selected="true"] { color: @tinta !important; }
  .stTabs [data-baseweb="tab-highlight"] { background-color: @acento; }
  /* El gráfico va dentro del vidrio; sin relleno extra, para que no aparezca un scroll de más */
  [data-testid="stPlotlyChart"] {
    background: @vidrio; border: 1.5px solid @borde; border-radius: 14px; box-shadow: @sombra; overflow: hidden;
  }
  .nota { color: @tenue; font-size: 0.82rem; margin-top: 6px; }
  .pie { color: @tenue; font-size: 0.82rem; text-align: center; margin: 28px 0 6px; }
  .pie a, .fuentes a, .nota a { color: @acento; }
  .fuentes table { width: 100%; border-collapse: collapse; color: @tinta; font-size: 0.9rem; }
  .fuentes td, .fuentes th { padding: 9px 12px; border-bottom: 1px solid @linea_tabs; text-align: left; vertical-align: top; }
  .fuentes th { color: @secundario; font-weight: 600; }
  .tabla-datos { overflow-x: auto; padding: 4px 8px; }
  .analisis { padding: 14px 18px; margin-bottom: 12px; color: @tinta; font-size: 0.92rem; line-height: 1.55; }
  .analisis p { margin: 6px 0 0; color: @tinta; }
  .tabla-datos table { font-size: 0.8rem; white-space: nowrap; }
  .tabla-datos td:not(:first-child), .tabla-datos th:not(:first-child) { text-align: right; }
</style>
"""
    for clave, valor in sorted(C.items(), key=lambda kv: -len(kv[0])):
        if isinstance(valor, str):
            css = css.replace("@" + clave, valor)
    st.markdown(css, unsafe_allow_html=True)


# ── Datos ─────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def leer() -> tuple[pd.DataFrame, pd.DataFrame]:
    mercado = pd.read_csv(os.environ.get("DASHBOARD_CSV") or DATOS / "mercado.csv")
    mercado["Fecha"] = pd.to_datetime(mercado["Fecha"])
    mercado = mercado.drop(columns=["ai_secciones"], errors="ignore").sort_values("Fecha").reset_index(drop=True)
    archivo_series = DATOS / "series.csv"
    if archivo_series.exists():
        series = pd.read_csv(archivo_series)
        series["Fecha"] = pd.to_datetime(series["Fecha"])
    else:
        series = pd.DataFrame(columns=["serie", "Fecha", "valor", "unidad", "fuente"])
    return mercado, series


def serie_larga(nombre: str) -> pd.Series:
    s = largas[largas["serie"] == nombre].set_index("Fecha")["valor"].astype(float).sort_index()
    return s[~s.index.duplicated(keep="last")]


# ── Formatos ──────────────────────────────────────────────────────────────────
def num(v: float, dec: int = 2) -> str:
    texto = f"{v:,.{dec}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".") if IDIOMA == "es" else texto


def pct(v: float, dec: int = 1, signo: bool = True) -> str:
    return ("+" if signo and v > 0 else "") + num(v, dec) + " %"


def fecha_corta(f: pd.Timestamp) -> str:
    return f"{f:%d/%m}" if IDIOMA == "es" else f"{f:%m/%d}"


def fecha_larga(f: pd.Timestamp) -> str:
    return f"{f:%d/%m/%Y}" if IDIOMA == "es" else f"{f:%m/%d/%Y}"


def mes_anio(f: pd.Timestamp) -> str:
    return f"{T['meses'][f.month - 1]} {f:%Y}"


def flecha(v: float) -> str:
    return "▲" if v > 0 else "▼" if v < 0 else "="


def valor_en(serie: pd.Series, fecha: pd.Timestamp):
    s = serie.dropna()
    s = s[s.index <= fecha]
    return None if s.empty else float(s.iloc[-1])


def linea_delta(d: float, etiqueta: str, suba_es_mala, puntos: bool, unidad: str, dec: int) -> str:
    if suba_es_mala is None or round(d, 6) == 0:
        clase = "neutro"
    else:
        clase = "baja" if (d > 0) == suba_es_mala else "sube"
    signo = "+" if d > 0 else ""
    texto = f"{flecha(d)} {signo}{num(d, dec)} {unidad}" if puntos else f"{flecha(d)} {pct(d)}"
    return f'<span class="{clase}"><b>{texto}</b></span> {etiqueta}'


def tarjeta(rotulo: str, valor: str, renglones: list[str]) -> str:
    return (f'<div class="vidrio tarjeta"><div class="rotulo">{rotulo}</div><div class="valor">{valor}</div>'
            f'<div class="delta">{"<br>".join(renglones)}</div></div>')


def tarjeta_diaria(rotulo, valor, serie, actual, suba_es_mala=None, puntos=False, unidad="pts", dec=0):
    renglones = []
    for etiqueta, fecha in fechas_ref.items():
        ref = valor_en(serie, fecha)
        if ref is None or (not puntos and ref == 0):
            continue
        d = actual - ref if puntos else (actual / ref - 1) * 100
        renglones.append(linea_delta(d, etiqueta, suba_es_mala, puntos, unidad, dec))
    return tarjeta(rotulo, valor, renglones)


# ── Gráficos ──────────────────────────────────────────────────────────────────
def _ticks(indice: pd.DatetimeIndex) -> dict:
    meses = T["meses"]
    dias = (indice.max() - indice.min()).days
    if dias <= 75:
        marcas = pd.date_range(indice.min().normalize(), indice.max(), freq="W-MON")
        return dict(tickvals=marcas, ticktext=[f"{d.day} {meses[d.month - 1]}" for d in marcas])
    if dias <= 550:
        marcas = pd.date_range(indice.min().to_period("M").to_timestamp() + pd.offsets.MonthBegin(1), indice.max(), freq="MS")
        return dict(tickvals=marcas, ticktext=[f"{meses[d.month - 1]} {d:%y}" for d in marcas])
    marcas = pd.date_range(indice.min().to_period("Q").to_timestamp(), indice.max(), freq="QS")
    marcas = marcas[marcas >= indice.min()]
    return dict(tickvals=marcas, ticktext=[f"{meses[d.month - 1]} {d:%y}" for d in marcas])


def _layout(fig: go.Figure, alto: int, prefijo: str, sufijo: str, rango=None, indice=None, titulo_y: str = "") -> go.Figure:
    eje = dict(showline=True, linecolor=C["eje"], linewidth=1.2, ticks="outside", tickcolor=C["eje"],
               gridcolor=C["grilla"], zeroline=False, tickfont=dict(color=C["secundario"], size=12))
    fig.update_xaxes(**eje)
    if indice is not None and len(indice):
        fig.update_xaxes(**_ticks(pd.DatetimeIndex(indice)))
    fig.update_yaxes(**eje, tickprefix=prefijo, ticksuffix=sufijo, separatethousands=True,
                     title=dict(text=titulo_y, font=dict(color=C["secundario"], size=12)))
    if rango:
        fig.update_yaxes(range=rango)
    fig.update_layout(
        height=alto, margin=dict(l=12, r=120, t=40, b=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans, Segoe UI, sans-serif", color=C["tinta"], size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=C["secundario"])),
        hovermode="x unified", separators=",." if IDIOMA == "es" else ".,",
        hoverlabel=dict(bgcolor=C["hover"], bordercolor=C["borde"], font=dict(color=C["tinta"])),
        bargap=0.25,
    )
    return fig


def _rango(valores: list, nunca_negativo: bool, incluir_cero: bool = False):
    if not valores:
        return None
    bajo, alto = min(valores), max(valores)
    if incluir_cero:
        bajo = min(bajo, 0)
    margen = (alto - bajo) * 0.08 or abs(alto) * 0.05 or 1
    piso = bajo - margen
    if nunca_negativo:
        piso = max(0, piso)
    return [piso, alto + margen]


def grafico(series: dict, *, prefijo="", sufijo="", dec=2, nunca_negativo=True, linea_cero=False,
            extremos=False, alto=430, titulo_y: str = "") -> go.Figure:
    """Líneas: ejes visibles, etiqueta del último valor de cada serie y escala pegada a los datos."""
    fig = go.Figure()
    valores, etiquetas, indice = [], [], None
    for i, (nombre, s) in enumerate(series.items()):
        s = s.dropna()
        if s.empty:
            continue
        color = C["series"][i % len(C["series"])]
        valores.extend(s.tolist())
        indice = s.index if indice is None else indice.union(s.index)
        fig.add_trace(go.Scatter(x=s.index, y=s.values, name=nombre, mode="lines", line=dict(color=color, width=2.4),
                                 hovertemplate=f"{nombre}: {prefijo}%{{y:,.{dec}f}}{sufijo}<extra></extra>"))
        etiquetas.append((s.index[-1], float(s.iloc[-1]), color))
        if extremos and len(series) == 1:
            for fecha, valor, abajo in ((s.idxmax(), s.max(), False), (s.idxmin(), s.min(), True)):
                if fecha == s.index[-1]:
                    continue
                fig.add_trace(go.Scatter(x=[fecha], y=[valor], mode="markers", showlegend=False, hoverinfo="skip",
                                         marker=dict(color=color, size=8, line=dict(color=C["papel"], width=1.5))))
                fig.add_annotation(x=fecha, y=valor, text=f"{T['min'] if abajo else T['max']} {prefijo}{num(valor, dec)}{sufijo}",
                                   showarrow=False, yshift=-16 if abajo else 16, font=dict(color=C["secundario"], size=11))
    rango = _rango(valores, nunca_negativo)
    if rango:
        separacion = 17 / (alto - 90) * (rango[1] - rango[0])
        etiquetas.sort(key=lambda e: e[1])
        posiciones = []
        for _, y, _ in etiquetas:
            posiciones.append(y if not posiciones or y - posiciones[-1] >= separacion else posiciones[-1] + separacion)
        for (x, y, color), y_etiqueta in zip(etiquetas, posiciones):
            fig.add_annotation(x=x, y=y_etiqueta, text=f"<b>{prefijo}{num(y, dec)}{sufijo}</b>",
                               showarrow=False, xanchor="left", xshift=8, font=dict(color=color, size=12))
    if linea_cero:
        fig.add_hline(y=0, line=dict(color=C["eje"], width=1, dash="dot"))
    return _layout(fig, alto, prefijo, sufijo, rango, indice, titulo_y)


def barras(series: dict, *, prefijo="", sufijo="", dec=1, linea: dict | None = None, alto=430,
           titulo_y: str = "") -> go.Figure:
    """Barras mensuales con la etiqueta de cada valor; opcionalmente una línea encima (eje propio)."""
    fig = go.Figure()
    valores, indice = [], None
    for i, (nombre, s) in enumerate(series.items()):
        s = s.dropna()
        if s.empty:
            continue
        valores.extend(s.tolist())
        indice = s.index if indice is None else indice.union(s.index)
        fig.add_trace(go.Bar(x=s.index, y=s.values, name=nombre, marker_color=C["series"][i % len(C["series"])],
                             text=[f"{prefijo}{num(v, dec)}{sufijo}" for v in s.values], textposition="outside",
                             textfont=dict(color=C["tinta"], size=13), cliponaxis=False,
                             hovertemplate=f"{nombre}: {prefijo}%{{y:,.{dec}f}}{sufijo}<extra></extra>"))
    rango = _rango(valores, nunca_negativo=True, incluir_cero=True)
    if rango:
        rango[1] = rango[1] * 1.08
    if linea:
        for nombre, s in linea.items():
            s = s.dropna()
            if s.empty:
                continue
            color = C["series"][1]
            fig.add_trace(go.Scatter(x=s.index, y=s.values, name=nombre, mode="lines+markers", yaxis="y2",
                                     line=dict(color=color, width=2.4), marker=dict(size=5),
                                     hovertemplate=f"{nombre}: %{{y:,.1f}} %<extra></extra>"))
            fig.add_annotation(x=s.index[-1], y=float(s.iloc[-1]), yref="y2", text=f"<b>{num(float(s.iloc[-1]), 1)} %</b>",
                               showarrow=False, xanchor="left", xshift=10, font=dict(color=color, size=12))
            fig.update_layout(yaxis2=dict(overlaying="y", side="right", showline=True, linecolor=C["eje"],
                                          ticksuffix=" %", showgrid=False, tickfont=dict(color=C["secundario"], size=12),
                                          rangemode="tozero"))
    fig = _layout(fig, alto, prefijo, sufijo, rango, indice, titulo_y)
    if linea:
        # _layout aplica la escala de las barras a todos los ejes: el de la línea va con la suya
        tope = max((float(s.max()) for s in linea.values() if not s.dropna().empty), default=1)
        fig.update_layout(yaxis2=dict(range=[0, tope * 1.15], tickprefix="", ticksuffix=" %", showgrid=False, title=None))
    if indice is not None and len(indice):
        meses = T["meses"]
        fig.update_xaxes(tickvals=list(indice), ticktext=[f"{meses[d.month - 1]} {d:%y}" for d in indice], tickangle=0)
    return fig


def mostrar(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


PLOTLY_JS = get_plotlyjs_version()  # la misma versión de Plotly.js que trae la librería de Python
ANCHO_POR_BARRA = 76  # lo que pide la etiqueta más larga ("US$ 489,6") y el mes del eje, sin pisarse


def mostrar_barras(fig: go.Figure) -> None:
    """Barras mensuales con un ancho mínimo por barra. Si no entran en la pantalla, el gráfico
    se desplaza de costado y arranca corrido del todo a la derecha, en el último mes."""
    meses = max((len(t.x) for t in fig.data if t.type == "bar"), default=0)
    ancho_minimo = meses * ANCHO_POR_BARRA + 110  # 110: los márgenes y la etiqueta de la línea a la derecha
    alto = fig.layout.height or 430
    # Al desplazar, el eje y queda fuera de la vista: cada barra ya lleva su valor, así que se ocultan
    # los números del eje (la grilla queda). Abajo, lugar fijo para los meses.
    fig.update_yaxes(showticklabels=False, ticks="", title=None)
    con_linea = any(t.type == "scatter" for t in fig.data)  # la línea lleva su último valor a la derecha
    fig.update_layout(margin=dict(l=12, r=90 if con_linea else 16, t=40, b=48), yaxis2=dict(showticklabels=False, ticks=""))
    fig.update_xaxes(automargin=True, tickfont=dict(size=13))
    fig.update_layout(height=alto, autosize=True, width=None)
    componentes.html(f"""
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.plot.ly/plotly-{PLOTLY_JS}.min.js" charset="utf-8"></script>
<style>
  html, body {{ margin: 0; background: transparent; font-family: "IBM Plex Sans", system-ui, sans-serif; }}
  .marco {{ background: {C["vidrio"]}; border: 1.5px solid {C["borde"]}; border-radius: 14px; overflow: hidden; }}
  .desliza {{ overflow-x: auto; overflow-y: hidden; scrollbar-color: {C["eje"]} transparent; }}
  .ancho {{ min-width: {ancho_minimo}px; height: {alto}px; }}
</style>
<div class="marco"><div class="desliza" id="desliza"><div class="ancho" id="grafico"></div></div></div>
<script>
  const fig = {fig.to_json()};
  const caja = document.getElementById("desliza"), destino = document.getElementById("grafico");
  const alFinal = () => {{ caja.scrollLeft = caja.scrollWidth; }};
  // Si la pestaña está oculta, el marco mide cero: Plotly dibujaría sin etiquetas y con la leyenda
  // encimada. Se dibuja recién cuando tiene ancho, y se ajusta si cambia.
  let dibujado = false, ancho = 0;
  new ResizeObserver(() => {{
    if (!caja.clientWidth || caja.clientWidth === ancho) return;
    ancho = caja.clientWidth;
    const listo = dibujado ? Plotly.Plots.resize(destino)
      : Plotly.newPlot(destino, fig.data, fig.layout, {{displayModeBar: false, responsive: true}});
    dibujado = true;
    Promise.resolve(listo).then(alFinal);
  }}).observe(caja);
</script>""", height=alto + 22)


def nota(texto: str) -> None:
    st.markdown(f'<div class="nota">{texto}</div>', unsafe_allow_html=True)


def resumen(nombre: str, s: pd.Series, prefijo="", sufijo="", dec=2) -> None:
    s = s.dropna()
    if not s.empty:
        nota(T["en_periodo"].format(serie=nombre, min=f"{prefijo}{num(s.min(), dec)}{sufijo}", fmin=fecha_larga(s.idxmin()),
                                    max=f"{prefijo}{num(s.max(), dec)}{sufijo}", fmax=fecha_larga(s.idxmax())))


# ══════════════════════════════════════════════════════════════════════════════
_estilos()
mercado, largas = leer()
if mercado.empty:
    st.error(T["sin_datos"])
    st.stop()
serie = mercado.set_index("Fecha")
ult = mercado.iloc[-1]
hoy = ult["Fecha"]
ayer = mercado["Fecha"].iloc[-2]
primero = mercado["Fecha"].min()
fechas_ref = {
    T["vs"].format(fecha=fecha_corta(ayer)): ayer,
    T["30d"]: hoy - pd.Timedelta(days=30),
    T["anio"]: pd.Timestamp(hoy.year - 1, 12, 31),
}

# Encabezado: logo y título alineados, y a la derecha el idioma
izquierda, botones = st.columns([6, 2.6], vertical_alignment="center")
with izquierda:
    st.markdown(f'<div class="encabezado"><img src="data:image/svg+xml;base64,{_logo()}" alt="GlobalAIze">'
                f'<div class="titulo">{T["titulo"]}</div></div>', unsafe_allow_html=True)
with botones:
    col_idioma, col_tema = st.columns([1.25, 1])
    with col_idioma:
        # Links y no un control de Streamlit: los emojis de bandera no se ven en Windows, así que van en SVG
        tema_url = "oscuro" if OSCURO else "claro"
        st.markdown('<div class="idiomas">' + "".join(
            f'<a href="?lang={codigo}&tema={tema_url}" target="_self" class="{"activo" if codigo == IDIOMA else ""}"'
            f' aria-label="{nombre}">{BANDERAS[codigo]}<span>{codigo.upper()}</span></a>'
            for codigo, nombre in (("es", "Español"), ("en", "English"))) + "</div>", unsafe_allow_html=True)
    with col_tema:
        oscuro, claro = T["oscuro"], T["claro"]
        elegido_tema = st.segmented_control("Tema / Theme", [oscuro, claro], default=oscuro if OSCURO else claro,
                                            label_visibility="collapsed", key=f"tema_{IDIOMA}")
    if elegido_tema and (elegido_tema == oscuro) != OSCURO:
        st.query_params["tema"] = "oscuro" if elegido_tema == oscuro else "claro"
        st.rerun()
st.markdown(f'<div class="bajada">{T["bajada"].format(fecha=fecha_larga(hoy), desde=fecha_larga(primero))}</div>',
            unsafe_allow_html=True)

# ── Tarjetas ──
brecha = (serie["TCV_Blue"] / serie["TCV_Billete"] - 1) * 100
tarjetas = [
    tarjeta_diaria(T["blue"], f"$ {num(ult['TCV_Blue'])}", serie["TCV_Blue"], ult["TCV_Blue"], suba_es_mala=True),
    tarjeta_diaria(T["mep"], f"$ {num(ult['TCV_MEP'])}", serie["TCV_MEP"], ult["TCV_MEP"], suba_es_mala=True),
    tarjeta_diaria(T["oficial"], f"$ {num(ult['TCV_Billete'])}", serie["TCV_Billete"], ult["TCV_Billete"], suba_es_mala=True),
    tarjeta_diaria(T["brecha"], pct(brecha.iloc[-1], signo=False), brecha, brecha.iloc[-1], suba_es_mala=True,
                   puntos=True, unidad="pp", dec=1),
    tarjeta_diaria(T["riesgo"], f"{num(ult['riesgo_pais'], 0)} pts", serie["riesgo_pais"], ult["riesgo_pais"],
                   suba_es_mala=True, puntos=True),
    tarjeta_diaria(T["badlar"], pct(ult["bcra_tea"], 2, signo=False), serie["bcra_tea"], ult["bcra_tea"],
                   puntos=True, unidad="pp", dec=2),
]
inflacion = serie_larga("inflacion_mensual")
interanual = serie_larga("inflacion_interanual")
if len(inflacion) >= 2:
    renglones = [linea_delta(inflacion.iloc[-1] - inflacion.iloc[-2], T["mes_ant"].format(mes=mes_anio(inflacion.index[-2])),
                             True, True, "pp", 1)]
    if not interanual.empty:
        renglones.append(T["12m"].format(pct=pct(interanual.iloc[-1], signo=False)))
    tarjetas.append(tarjeta(f"{T['inflacion']} ({mes_anio(inflacion.index[-1])})", pct(inflacion.iloc[-1], signo=False),
                            renglones))
btc = serie_larga("bitcoin")
if not btc.empty:
    tarjetas.append(tarjeta_diaria(T["bitcoin"], f"US$ {num(btc.iloc[-1], 0)}", btc, btc.iloc[-1]))
st.markdown(f'<div class="tarjetas">{"".join(tarjetas)}</div>', unsafe_allow_html=True)
nota(T["nota_tarjetas"].format(ayer=fecha_larga(ayer), anio=hoy.year - 1))

# ── Período ──
periodos = {T["p1m"]: 1, T["p3m"]: 3, T["p6m"]: 6, T["p1a"]: 12, T["pytd"]: "ytd",
            T["ptodo"].format(desde=mes_anio(primero)): None}
st.write("")
elegido = st.segmented_control(T["periodo"], list(periodos), default=T["p6m"], key=f"periodo_{IDIOMA}")
meses = periodos.get(elegido or T["p6m"], 6)
if meses == "ytd":
    desde = pd.Timestamp(hoy.year, 1, 1)
elif meses is None:
    desde = primero
else:
    desde = hoy - pd.DateOffset(months=meses)
desde_mensual = min(desde, hoy - pd.DateOffset(months=12))
p = serie[serie.index >= desde]


def recorte(s: pd.Series, mensual: bool = False) -> pd.Series:
    return s[s.index >= (desde_mensual if mensual else desde)]


pest = st.tabs(T["pest"])

with pest[0]:  # Oficiales
    opciones = ["TCV_Billete", "TCC_Billete", "TCV_Divisas", "TCC_Divisas", "Solidario", "tipo_cambio_mayorista"]
    datos = {c: (p[c] if c in p else recorte(serie_larga(c))) for c in opciones}
    elegidas = st.multiselect(T["sel_oficiales"], [N[c] for c in opciones],
                              default=[N["TCV_Billete"], N["tipo_cambio_mayorista"], N["Solidario"]], key=f"of_{IDIOMA}")
    claves = [c for c in opciones if N[c] in elegidas]
    if claves:
        mostrar(grafico({N[c]: datos[c] for c in claves}, prefijo="$ "))
        resumen(N[claves[0]], datos[claves[0]], "$ ")
    else:
        st.info(T["elegi"])

with pest[1]:  # Paralelos
    opciones = ["TCV_Blue", "TCC_Blue", "TCV_MEP", "TCV_Euro", "TCC_Euro"]
    elegidas = st.multiselect(T["sel_paralelos"], [N[c] for c in opciones],
                              default=[N["TCV_Blue"], N["TCV_MEP"], N["TCV_Euro"]], key=f"par_{IDIOMA}")
    claves = [c for c in opciones if N[c] in elegidas]
    if claves:
        mostrar(grafico({N[c]: p[c] for c in claves}, prefijo="$ "))
        resumen(N[claves[0]], p[claves[0]], "$ ")
    else:
        st.info(T["elegi"])

with pest[2]:  # Brechas
    mayorista = recorte(serie_larga("tipo_cambio_mayorista")).reindex(p.index).ffill()
    brechas = {
        "g_blue_of": (p["TCV_Blue"] / p["TCV_Billete"] - 1) * 100,
        "g_mep_div": (p["TCV_MEP"] / p["TCV_Divisas"] - 1) * 100,
        "g_blue_mep": (p["TCV_Blue"] / p["TCV_MEP"] - 1) * 100,
        "g_sol_blue": (p["Solidario"] / p["TCV_Blue"] - 1) * 100,
        "g_of_may": (p["TCV_Billete"] / mayorista - 1) * 100,
    }
    elegidas = st.multiselect(T["sel_brechas"], [N[c] for c in brechas],
                              default=[N["g_blue_of"], N["g_mep_div"], N["g_blue_mep"]], key=f"br_{IDIOMA}")
    claves = [c for c in brechas if N[c] in elegidas]
    if claves:
        mostrar(grafico({N[c]: brechas[c] for c in claves}, sufijo=" %", dec=1, nunca_negativo=False, linea_cero=True))
        nota(T["nota_brechas"])
    else:
        st.info(T["elegi"])

with pest[3]:  # Riesgo país
    mostrar(grafico({N["riesgo_pais"]: p["riesgo_pais"]}, sufijo=" pts", dec=0, extremos=True))
    resumen(N["riesgo_pais"], p["riesgo_pais"], sufijo=" pts", dec=0)

with pest[4]:  # Tasas
    mostrar(grafico({N["bcra_tea"]: p["bcra_tea"], N["fed_tea"]: p["fed_tea"], N["dif"]: p["bcra_tea"] - p["fed_tea"]},
                    sufijo=" %"))
    nota(T["nota_tasas"])

with pest[5]:  # Inflación
    mostrar_barras(barras({N["inflacion_mensual"]: recorte(inflacion, True)}, sufijo=" %",
                   linea={N["inflacion_interanual"]: recorte(interanual, True)}))
    nota(T["nota_inflacion"] + " " + T["nota_mensual"])

with pest[6]:  # Dinero y BCRA
    opciones = ["base_monetaria", "circulacion_monetaria", "billetes_publico", "m2", "m2_transaccional_privado",
                "prestamos_sector_privado", "letras_bcra_pesos", "letras_bcra_moneda_extranjera", "adelantos_transitorios"]
    elegidas = st.multiselect(T["sel_dinero"], [N[c] for c in opciones],
                              default=[N["base_monetaria"], N["m2"], N["prestamos_sector_privado"]], key=f"din_{IDIOMA}")
    claves = [c for c in opciones if N[c] in elegidas]
    if claves:
        # millones de pesos → billones (millones de millones)
        mostrar(grafico({N[c]: recorte(serie_larga(c)) / 1e6 for c in claves}, prefijo="$ ", dec=1, titulo_y=T["billones"]))
        nota(T["nota_dinero"])
    else:
        st.info(T["elegi"])

with pest[7]:  # Deuda
    deuda = recorte(serie_larga("deuda_bruta_tesoro"), True) / 1e3
    mostrar_barras(barras({N["deuda_bruta_tesoro"]: deuda}, prefijo="US$ ", dec=1, titulo_y=T["usd_bn"]))
    nota(T["nota_deuda"] + " " + T["nota_mensual"])

with pest[8]:  # Bitcoin
    mostrar(grafico({N["bitcoin"]: recorte(btc)}, prefijo="US$ ", dec=0, extremos=True))
    resumen(N["bitcoin"], recorte(btc), "US$ ", dec=0)

with pest[9]:  # Análisis de IA
    if T["ia_idioma"]:
        nota(T["ia_idioma"])
    parrafos = p["ai_paragraph"].dropna() if "ai_paragraph" in p else pd.Series(dtype=str)
    parrafos = parrafos[parrafos.astype(str).str.strip() != ""].sort_index(ascending=False)
    if parrafos.empty:
        st.info(T["sin_ia"])
    bloques = "".join(f'<div class="vidrio analisis"><b>{fecha_larga(fecha)}</b><p>{html.escape(str(parrafo))}</p></div>'
                      for fecha, parrafo in parrafos.head(10).items())
    st.markdown(bloques, unsafe_allow_html=True)
    nota(T["nota_ia"])

with pest[10]:  # Datos (solo lo publicado, desde el 1 de enero de hace dos años)
    visibles = [c for c in p.columns if c not in ("ai_paragraph", "ai_model")]
    recientes = p[visibles].sort_index(ascending=False).head(30)
    encabezado = "".join(f"<th>{c}</th>" for c in ["Fecha" if IDIOMA == "es" else "Date", *[N.get(c, c) for c in visibles]])
    filas = "".join("<tr><td>" + fecha_larga(f) + "</td>" + "".join(
        f"<td>{num(v, 0 if c == 'riesgo_pais' else 2) if isinstance(v, (int, float)) and pd.notna(v) else ''}</td>"
        for c, v in zip(visibles, fila)) + "</tr>"
        for f, fila in zip(recientes.index, recientes.values))
    st.markdown(f'<div class="vidrio fuentes tabla-datos"><table><tr>{encabezado}</tr>{filas}</table></div>',
                unsafe_allow_html=True)
    st.download_button(T["descargar"], p[visibles].to_csv().encode("utf-8"), "seguimiento_macroeconomico.csv", "text/csv")
    nota(T["nota_datos"].format(desde=fecha_larga(primero)))

with pest[11]:  # Fuentes
    filas = "".join(f"<tr><td>{f}</td><td>{q}</td></tr>" for f, q in FUENTES[IDIOMA])
    st.markdown(f'<div class="vidrio fuentes" style="padding:6px 10px"><table><tr><th>{T["fuente"]}</th><th>{T["aporta"]}</th></tr>'
                f"{filas}</table></div>", unsafe_allow_html=True)
    nota(T["nota_fuentes"].format(repo=REPO))

st.markdown(f'<div class="pie">{T["pie"].format(repo=REPO)}</div>', unsafe_allow_html=True)
