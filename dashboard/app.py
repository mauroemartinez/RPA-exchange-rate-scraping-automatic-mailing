"""Tablero de seguimiento macroeconómico, con la marca de GlobalAIze.

Lee el histórico de Fact_Mercado_Macro de una de tres fuentes, en este orden:
1. DASHBOARD_CSV (variable de entorno): un CSV cualquiera, por ejemplo el adjunto del mail.
2. DASHBOARD_DB_URL (secrets de Streamlit o entorno): un usuario de solo lectura, en
   una transacción READ ONLY.
3. dashboard/data/mercado.csv: la copia diaria que sube el workflow datos-dashboard.yml.
   Es la que usa el tablero publicado: no necesita credenciales y no expone la base.
En la PC propia, si no hay ninguna de las tres, usa SUPABASE_DB_URL del .env.

No importa reporte/config.py a propósito: config exige todas las credenciales del
pipeline (mail, Gemini, FRED) y un tablero publicado no tiene por qué tenerlas.

Uso:
    pip install -r dashboard/requirements.txt
    streamlit run dashboard/app.py
"""

import base64
import logging
import os
import re
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import dotenv_values
from sqlalchemy import create_engine, text

RAIZ = Path(__file__).resolve().parent.parent
AQUI = Path(__file__).resolve().parent
TABLA = "Fact_Mercado_Macro"
CSV_PUBLICADO = AQUI / "data" / "mercado.csv"
REPO = "https://github.com/mauroemartinez/RPA-exchange-rate-scraping-automatic-mailing"

# ── Marca GlobalAIze ──
TINTA = "#F0EEE9"
SECUNDARIO = "#BBC5D1"
EJE = "#8D9AA8"
GRILLA = "rgba(255,255,255,0.08)"
SERIES = ["#0DA4CF", "#795EC9", "#A69722", "#4170CB", "#C13234", "#3BAB8D", "#B33879", "#47AB4F"]

OFICIALES = {
    "Billete BNA (venta)": "TCV_Billete",
    "Billete BNA (compra)": "TCC_Billete",
    "Divisas BNA (venta)": "TCV_Divisas",
    "Divisas BNA (compra)": "TCC_Divisas",
    "Solidario": "Solidario",
}
PARALELOS = {
    "Blue (venta)": "TCV_Blue",
    "Blue (compra)": "TCC_Blue",
    "MEP": "TCV_MEP",
    "Euro blue (venta)": "TCV_Euro",
    "Euro blue (compra)": "TCC_Euro",
}
FUENTES = [
    ("Banco Nación", "Dólar minorista billete y divisa, compra y venta; el solidario se calcula sobre el billete"),
    ("DolarHoy", "Dólar paralelo (blue), compra y venta"),
    ("Ámbito", "Dólar MEP y euro blue"),
    ("ArgentinaDatos", "Riesgo país, con su fecha de publicación"),
    ("API de estadísticas del BCRA", "Tasa BADLAR"),
    ("St. Louis FRED", "Tasa efectiva de los fondos federales de EE. UU. (si FRED falla, la publica la Fed de Nueva York)"),
    ("Google Gemini", "Los análisis de IA, sobre las cifras que calcula el pipeline"),
]

st.set_page_config(
    page_title="Seguimiento macroeconómico | GlobalAIze",
    page_icon=str(AQUI / "assets" / "globalaize-favicon.svg"),
    layout="wide",
    initial_sidebar_state="collapsed",
)


def _svg_base64(nombre: str) -> str:
    return base64.b64encode((AQUI / "assets" / nombre).read_bytes()).decode()


def _estilos() -> None:
    st.markdown(
        """
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,400;6..72,500&display=swap" rel="stylesheet">
<style>
  .stApp {
    background:
      radial-gradient(40% 55% at 20% 38%, rgb(34 181 225 / .17), transparent 70%),
      radial-gradient(40% 55% at 82% 78%, rgb(31 79 168 / .20), transparent 70%),
      radial-gradient(45% 35% at 52% 10%, rgb(16 52 140 / .20), transparent 70%),
      #040F23;
    background-attachment: fixed;
  }
  html, body, [class*="st-"], .stMarkdown, .stTabs, button, input, label {
    font-family: "IBM Plex Sans", system-ui, "Segoe UI", sans-serif;
  }
  h1, h2, h3, .titulo { font-family: "Newsreader", Georgia, serif !important; font-weight: 500 !important; }
  header[data-testid="stHeader"] { background: transparent; }
  [data-testid="stToolbar"], [data-testid="stDecoration"], footer { display: none; }
  .block-container { padding-top: 1.6rem; max-width: 1400px; }
  .encabezado { display: flex; align-items: center; gap: 18px; margin-bottom: 2px; flex-wrap: wrap; }
  .encabezado img { height: 34px; }
  .encabezado .titulo { font-size: 2.1rem; color: #F0EEE9; line-height: 1.1; }
  .bajada { color: #BBC5D1; font-size: 0.92rem; margin: 6px 0 18px; }
  .vidrio {
    background: rgb(5 30 69 / .70);
    -webkit-backdrop-filter: blur(36px) saturate(120%);
    backdrop-filter: blur(36px) saturate(120%);
    border: 1.5px solid rgb(255 255 255 / .10);
    border-radius: 14px;
    box-shadow: 0 10px 28px rgba(0, 0, 0, 0.25);
  }
  .tarjetas { display: grid; grid-template-columns: repeat(auto-fit, minmax(175px, 1fr)); gap: 12px; margin-bottom: 8px; }
  .tarjeta { padding: 14px 16px; }
  .tarjeta .rotulo { color: #BBC5D1; font-size: 0.78rem; letter-spacing: .04em; text-transform: uppercase; font-weight: 600; }
  .tarjeta .valor { color: #F0EEE9; font-size: 1.7rem; font-weight: 600; margin: 2px 0 6px; }
  .tarjeta .delta { font-size: 0.8rem; color: #BBC5D1; line-height: 1.55; }
  .tarjeta .delta b { font-weight: 600; }
  .sube { color: #62D286; } .baja { color: #EF6661; } .neutro { color: #F0EEE9; }
  .stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid #2A394D; flex-wrap: wrap; }
  .stTabs [data-baseweb="tab"] { color: #BBC5D1; font-weight: 500; padding: 8px 14px; }
  .stTabs [aria-selected="true"] { color: #F0EEE9 !important; }
  .stTabs [data-baseweb="tab-highlight"] { background-color: #0DA4CF; }
  [data-testid="stPlotlyChart"] {
    background: rgb(5 30 69 / .55); border: 1.5px solid rgb(255 255 255 / .08);
    border-radius: 14px; padding: 8px 6px 2px;
  }
  .nota { color: #8D9AA8; font-size: 0.82rem; margin-top: 4px; }
  .ia { padding: 16px 18px; margin-bottom: 12px; color: #F0EEE9; line-height: 1.55; }
  .ia .fecha { color: #1FB5E3; font-weight: 600; font-size: 0.85rem; margin-bottom: 4px; }
  .pie { color: #8D9AA8; font-size: 0.82rem; text-align: center; margin: 28px 0 6px; }
  .pie a, .fuentes a, .nota a { color: #1FB5E3; }
  .fuentes table { width: 100%; border-collapse: collapse; color: #F0EEE9; font-size: 0.9rem; }
  .fuentes td, .fuentes th { padding: 9px 12px; border-bottom: 1px solid #2A394D; text-align: left; vertical-align: top; }
  .fuentes th { color: #BBC5D1; font-weight: 600; }
</style>
""",
        unsafe_allow_html=True,
    )


def _secreto(nombre: str) -> str | None:
    """Un valor de los secrets de Streamlit o del entorno."""
    try:
        if nombre in st.secrets:
            return st.secrets[nombre]
    except Exception:
        pass  # sin secrets.toml
    return os.environ.get(nombre)


def _leer_base(url: str) -> pd.DataFrame:
    try:
        engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 30})
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            df = pd.read_sql_query(text(f'SELECT * FROM "{TABLA}" ORDER BY "Fecha"'), conn)
        engine.dispose()
        return df
    except Exception:
        # El detalle queda en el log del servidor, no en la página
        logging.getLogger(__name__).exception("No se pudieron leer los datos")
        st.error("No se pudieron leer los datos. Probá de nuevo en un rato.")
        st.stop()


@st.cache_data(ttl=3600, show_spinner="Leyendo el histórico...")
def historico() -> pd.DataFrame:
    if os.environ.get("DASHBOARD_CSV"):
        df = pd.read_csv(os.environ["DASHBOARD_CSV"])
    elif _secreto("DASHBOARD_DB_URL"):
        df = _leer_base(_secreto("DASHBOARD_DB_URL"))
    elif CSV_PUBLICADO.exists():
        df = pd.read_csv(CSV_PUBLICADO)
    else:
        url = dotenv_values(RAIZ / ".env").get("SUPABASE_DB_URL")
        if not url:
            st.error("No hay datos para mostrar.")
            st.stop()
        df = _leer_base(url)
    df["Fecha"] = pd.to_datetime(df["Fecha"])
    return df.drop(columns=["ai_secciones"], errors="ignore").sort_values("Fecha").reset_index(drop=True)


# ── Formatos en castellano ──
def num(v: float, dec: int = 2) -> str:
    return f"{v:,.{dec}f}".replace(",", "§").replace(".", ",").replace("§", ".")


def pct(v: float, dec: int = 1, signo: bool = True) -> str:
    return (f"{v:+.{dec}f}" if signo else f"{v:.{dec}f}").replace(".", ",") + " %"


def flecha(v: float) -> str:
    return "▲" if v > 0 else "▼" if v < 0 else "="


def valor_en(serie: pd.Series, fecha: pd.Timestamp) -> float | None:
    """El último valor disponible hasta esa fecha (incluida)."""
    s = serie.dropna()
    s = s[s.index <= fecha]
    return None if s.empty else float(s.iloc[-1])


def variacion(serie: pd.Series, fecha_ref: pd.Timestamp, actual: float, puntos: bool = False):
    ref = valor_en(serie, fecha_ref)
    if ref is None or (not puntos and ref == 0):
        return None
    return actual - ref if puntos else (actual / ref - 1) * 100


def tarjeta(rotulo: str, valor: str, serie: pd.Series, fechas: dict, actual: float, puntos: bool = False,
            suba_es_mala: bool | None = None, unidad_puntos: str = "pts", dec_puntos: int = 0) -> str:
    """Una tarjeta con el valor y su variación contra el día hábil anterior, 30 días atrás y fin del año pasado."""
    renglones = []
    for nombre, fecha in fechas.items():
        d = variacion(serie, fecha, actual, puntos)
        if d is None:
            continue
        if suba_es_mala is None or round(d, 4) == 0:
            clase = "neutro"
        else:
            clase = "baja" if (d > 0) == suba_es_mala else "sube"
        texto = f"{flecha(d)} {num(d, dec_puntos)} {unidad_puntos}" if puntos else f"{flecha(d)} {pct(d)}"
        renglones.append(f'<span class="{clase}"><b>{texto}</b></span> {nombre}')
    return (f'<div class="vidrio tarjeta"><div class="rotulo">{rotulo}</div>'
            f'<div class="valor">{valor}</div><div class="delta">{"<br>".join(renglones)}</div></div>')


MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def _ticks_en_castellano(indice: pd.DatetimeIndex) -> dict:
    """Marcas del eje X en castellano: por mes, trimestre o año según lo largo del período."""
    dias = (indice.max() - indice.min()).days
    if dias <= 75:
        marcas = pd.date_range(indice.min().normalize(), indice.max(), freq="W-MON")
        return dict(tickvals=marcas, ticktext=[f"{d.day} {MESES[d.month - 1]}" for d in marcas])
    if dias <= 550:
        marcas = pd.date_range(indice.min().to_period("M").to_timestamp() + pd.offsets.MonthBegin(1), indice.max(), freq="MS")
        return dict(tickvals=marcas, ticktext=[f"{MESES[d.month - 1]} {d:%y}" for d in marcas])
    if dias <= 4 * 365:
        marcas = pd.date_range(indice.min(), indice.max(), freq="QS")
        return dict(tickvals=marcas, ticktext=[f"{MESES[d.month - 1]} {d:%y}" for d in marcas])
    paso = max(1, round(dias / 365 / 10))
    marcas = pd.date_range(indice.min(), indice.max(), freq=f"{paso}YS")
    return dict(tickvals=marcas, ticktext=[f"{d:%Y}" for d in marcas])


def grafico(series: dict, *, prefijo: str = "", sufijo: str = "", decimales: int = 2,
            nunca_negativo: bool = True, linea_cero: bool = False, alto: int = 430,
            extremos: bool = False) -> go.Figure:
    """Líneas con la marca: ejes visibles, etiqueta del último valor de cada serie y escala pegada a los datos."""
    fig = go.Figure()
    valores, etiquetas, indice = [], [], None
    for i, (nombre, s) in enumerate(series.items()):
        s = s.dropna()
        if s.empty:
            continue
        color = SERIES[i % len(SERIES)]
        valores.extend(s.tolist())
        indice = s.index if indice is None else indice.union(s.index)
        fig.add_trace(go.Scatter(
            x=s.index, y=s.values, name=nombre, mode="lines", line=dict(color=color, width=2.4),
            hovertemplate=f"{nombre}: {prefijo}%{{y:,.{decimales}f}}{sufijo}<extra></extra>",
        ))
        etiquetas.append((s.index[-1], float(s.iloc[-1]), color))
        if extremos and len(series) == 1:
            # Etiquetas de datos del máximo y el mínimo del período
            for fecha, valor, abajo in ((s.idxmax(), s.max(), False), (s.idxmin(), s.min(), True)):
                if fecha == s.index[-1]:
                    continue  # el último valor ya tiene su etiqueta
                fig.add_trace(go.Scatter(x=[fecha], y=[valor], mode="markers", showlegend=False, hoverinfo="skip",
                                         marker=dict(color=color, size=8, line=dict(color="#040F23", width=1.5))))
                fig.add_annotation(x=fecha, y=valor, text=f"{'mín.' if abajo else 'máx.'} {prefijo}{num(valor, decimales)}{sufijo}",
                                   showarrow=False, yshift=-16 if abajo else 16, font=dict(color=SECUNDARIO, size=11))
    if valores:
        bajo, alto_v = min(valores), max(valores)
        margen = (alto_v - bajo) * 0.08 or abs(alto_v) * 0.05 or 1
        piso = bajo - margen
        if nunca_negativo:
            piso = max(0, piso)
        techo = alto_v + margen
        fig.update_yaxes(range=[piso, techo])
        # Etiqueta del último valor de cada serie, separadas para que no se pisen
        alto_px = alto - 80
        separacion = 17 / alto_px * (techo - piso)
        etiquetas.sort(key=lambda e: e[1])
        posiciones = []
        for _, y, _ in etiquetas:
            posiciones.append(y if not posiciones or y - posiciones[-1] >= separacion else posiciones[-1] + separacion)
        for (x, y, color), y_etiqueta in zip(etiquetas, posiciones):
            fig.add_annotation(x=x, y=y_etiqueta, text=f"<b>{prefijo}{num(y, decimales)}{sufijo}</b>",
                               showarrow=False, xanchor="left", xshift=8, font=dict(color=color, size=12))
    if indice is not None and len(indice):
        fig.update_xaxes(**_ticks_en_castellano(indice))
    if linea_cero:
        fig.add_hline(y=0, line=dict(color=EJE, width=1, dash="dot"))
    eje = dict(showline=True, linecolor=EJE, linewidth=1.2, ticks="outside", tickcolor=EJE,
               gridcolor=GRILLA, zeroline=False, tickfont=dict(color=SECUNDARIO, size=12))
    fig.update_xaxes(**eje)
    fig.update_yaxes(**eje, tickprefix=prefijo, ticksuffix=sufijo, separatethousands=True)
    fig.update_layout(
        height=alto, margin=dict(l=10, r=110, t=36, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Sans, Segoe UI, sans-serif", color=TINTA, size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, font=dict(color=SECUNDARIO)),
        hovermode="x unified", separators=",.",
        hoverlabel=dict(bgcolor="#051E45", bordercolor="#2A394D", font=dict(color=TINTA)),
    )
    return fig


def mostrar(fig: go.Figure) -> None:
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})


def resumen_periodo(s: pd.Series, prefijo: str = "", sufijo: str = "", dec: int = 2) -> str:
    s = s.dropna()
    if s.empty:
        return ""
    return (f'<div class="nota">En el período: mínimo {prefijo}{num(s.min(), dec)}{sufijo} ({s.idxmin():%d/%m/%Y}), '
            f'máximo {prefijo}{num(s.max(), dec)}{sufijo} ({s.idxmax():%d/%m/%Y}).</div>')


def _sin_markdown(texto: str) -> str:
    """El texto de Gemini tal cual: sin que un link, un encabezado o un $ se interpreten como formato."""
    return re.sub(r"([\\`*_{}\[\]()#+\-.!|<>~$])", r"\\\1", texto)


# ══════════════════════════════════════════════════════════════════════════════
_estilos()
df = historico()
ult = df.iloc[-1]
hoy = ult["Fecha"]
serie = df.set_index("Fecha")
dia_anterior = df["Fecha"].iloc[-2]
fechas_ref = {
    f"vs. {dia_anterior:%d/%m}": dia_anterior,
    "en 30 días": hoy - pd.Timedelta(days=30),
    "en el año": pd.Timestamp(hoy.year - 1, 12, 31),
}

ruedas = num(len(df), 0)
st.markdown(
    f'<div class="encabezado"><img src="data:image/svg+xml;base64,{_svg_base64("globalaize-logo-horizontal-es-dark.svg")}" alt="GlobalAIze">'
    f'<div class="titulo">Seguimiento macroeconómico de Argentina</div></div>'
    f'<div class="bajada">Dólares, brechas, riesgo país y tasas, todos los días hábiles. Último dato: <b>{hoy:%d/%m/%Y}</b> · '
    f'{ruedas} ruedas desde {df["Fecha"].min():%Y}.</div>',
    unsafe_allow_html=True,
)

# ── Tarjetas del día ──
brecha = (serie["TCV_Blue"] / serie["TCV_Billete"] - 1) * 100
tarjetas = [
    tarjeta("Dólar blue (venta)", f"$ {num(ult['TCV_Blue'])}", serie["TCV_Blue"], fechas_ref, ult["TCV_Blue"]),
    tarjeta("Dólar MEP", f"$ {num(ult['TCV_MEP'])}", serie["TCV_MEP"], fechas_ref, ult["TCV_MEP"]),
    tarjeta("Oficial BNA (venta)", f"$ {num(ult['TCV_Billete'])}", serie["TCV_Billete"], fechas_ref, ult["TCV_Billete"]),
    tarjeta("Brecha blue vs. oficial", pct(brecha.iloc[-1], signo=False), brecha, fechas_ref, brecha.iloc[-1],
            puntos=True, suba_es_mala=True, unidad_puntos="pp", dec_puntos=1),
    tarjeta("Riesgo país", f"{num(ult['riesgo_pais'], 0)} pts", serie["riesgo_pais"], fechas_ref, ult["riesgo_pais"],
            puntos=True, suba_es_mala=True),
    tarjeta("BADLAR (TEA)", pct(ult["bcra_tea"], 2, signo=False), serie["bcra_tea"], fechas_ref, ult["bcra_tea"],
            puntos=True, unidad_puntos="pp", dec_puntos=2),
]
st.markdown(f'<div class="tarjetas">{"".join(tarjetas)}</div>', unsafe_allow_html=True)
st.markdown(f'<div class="nota">Variaciones contra el día hábil anterior ({dia_anterior:%d/%m/%Y}), contra 30 días atrás '
            f'y contra el cierre del año pasado (31/12/{hoy.year - 1}). En riesgo país y brecha, subir es malo (rojo) y bajar '
            'es bueno (verde); en los dólares y las tasas, la flecha solo dice si subió o bajó. "pp" son puntos '
            'porcentuales.</div>', unsafe_allow_html=True)

# ── Período (vale para todos los gráficos) ──
PERIODOS = {"1 mes": 1, "3 meses": 3, "6 meses": 6, "1 año": 12, "En el año": "ytd", "2 años": 24, "5 años": 60, "Todo": None}
st.write("")
elegido = st.segmented_control("Período de los gráficos", list(PERIODOS), default="6 meses", key="periodo")
meses = PERIODOS.get(elegido or "6 meses")
if meses == "ytd":
    desde = pd.Timestamp(hoy.year, 1, 1)
elif meses is None:
    desde = df["Fecha"].min()
else:
    desde = hoy - pd.DateOffset(months=meses)
p = serie[serie.index >= desde]

pest = st.tabs(["Oficiales", "Paralelos", "Brechas", "Riesgo país", "Tasas", "Análisis de IA", "Datos", "Fuentes"])

with pest[0]:
    elegidas = st.multiselect("Cotizaciones oficiales", list(OFICIALES),
                              default=["Billete BNA (venta)", "Divisas BNA (venta)", "Solidario"], key="oficiales")
    if elegidas:
        mostrar(grafico({e: p[OFICIALES[e]] for e in elegidas}, prefijo="$ "))
        st.markdown(resumen_periodo(p[OFICIALES[elegidas[0]]], "$ ").replace("En el período", f"{elegidas[0]}, en el período"),
                    unsafe_allow_html=True)
    else:
        st.info("Elegí al menos una cotización.")

with pest[1]:
    elegidas = st.multiselect("Cotizaciones paralelas", list(PARALELOS),
                              default=["Blue (venta)", "MEP", "Euro blue (venta)"], key="paralelos")
    if elegidas:
        mostrar(grafico({e: p[PARALELOS[e]] for e in elegidas}, prefijo="$ "))
        st.markdown(resumen_periodo(p[PARALELOS[elegidas[0]]], "$ ").replace("En el período", f"{elegidas[0]}, en el período"),
                    unsafe_allow_html=True)
    else:
        st.info("Elegí al menos una cotización.")

with pest[2]:
    brechas = {
        "Blue vs. oficial BNA": (p["TCV_Blue"] / p["TCV_Billete"] - 1) * 100,
        "MEP vs. divisas BNA": (p["TCV_MEP"] / p["TCV_Divisas"] - 1) * 100,
        "Blue vs. MEP": (p["TCV_Blue"] / p["TCV_MEP"] - 1) * 100,
        "Solidario vs. blue": (p["Solidario"] / p["TCV_Blue"] - 1) * 100,
    }
    elegidas = st.multiselect("Brechas", list(brechas), default=["Blue vs. oficial BNA", "MEP vs. divisas BNA", "Blue vs. MEP"],
                              key="brechas")
    if elegidas:
        mostrar(grafico({e: brechas[e] for e in elegidas}, sufijo=" %", decimales=1, nunca_negativo=False, linea_cero=True))
        st.markdown('<div class="nota">Cuánto más caro está el primero que el segundo, en porcentaje. Negativo quiere decir '
                    'que está más barato.</div>', unsafe_allow_html=True)
    else:
        st.info("Elegí al menos una brecha.")

with pest[3]:
    mostrar(grafico({"Riesgo país": p["riesgo_pais"]}, sufijo=" pts", decimales=0, extremos=True))
    st.markdown(resumen_periodo(p["riesgo_pais"], sufijo=" pts", dec=0), unsafe_allow_html=True)

with pest[4]:
    mostrar(grafico({"BADLAR (TEA)": p["bcra_tea"], "FED (EFFR)": p["fed_tea"],
                     "Diferencial BADLAR − FED": p["bcra_tea"] - p["fed_tea"]}, sufijo=" %"))
    st.markdown('<div class="nota">Tasas anuales efectivas. El diferencial, en puntos porcentuales, es cuánto más paga un '
                'plazo fijo en pesos que la tasa de referencia de EE. UU., antes de descontar la devaluación.</div>',
                unsafe_allow_html=True)

with pest[5]:
    parrafos = p["ai_paragraph"].dropna() if "ai_paragraph" in p else pd.Series(dtype=str)
    parrafos = parrafos[parrafos.astype(str).str.strip() != ""].sort_index(ascending=False)
    if parrafos.empty:
        st.info("No hay análisis de IA en el período.")
    for fecha, parrafo in parrafos.head(10).items():
        with st.container(border=True):
            st.markdown(f"**{fecha:%d/%m/%Y}**")
            st.markdown(_sin_markdown(str(parrafo)))
    st.markdown('<div class="nota">Escritos por IA sobre las cifras que calcula el pipeline: la IA comenta los números, '
                'no los inventa.</div>', unsafe_allow_html=True)

with pest[6]:
    visibles = [c for c in p.columns if c not in ("ai_paragraph", "ai_model")]
    st.dataframe(p[visibles].sort_index(ascending=False), width="stretch")
    st.download_button("Descargar CSV del período", p[visibles].to_csv().encode("utf-8"),
                       "seguimiento_macroeconomico.csv", "text/csv")

with pest[7]:
    filas = "".join(f"<tr><td>{f}</td><td>{q}</td></tr>" for f, q in FUENTES)
    st.markdown(f'<div class="vidrio fuentes" style="padding:6px 10px"><table><tr><th>Fuente</th><th>Qué aporta</th></tr>'
                f"{filas}</table></div>"
                '<div class="nota">Cada valor se guarda con la fecha y la unidad de su fuente. Cómo se consigue y se valida '
                f'cada serie está en el <a href="{REPO}" target="_blank">repositorio</a>.</div>',
                unsafe_allow_html=True)

st.markdown(
    f'<div class="pie">Hecho por <a href="https://www.globalaize.com" target="_blank">GlobalAIze</a>: agentes de IA, '
    f'automatizaciones y análisis de datos. Código abierto en <a href="{REPO}" target="_blank">GitHub</a>.</div>',
    unsafe_allow_html=True,
)
