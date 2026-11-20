"""Marca GlobalAIze para los gráficos y la presentación: colores, tipografías y el vidrio azul.

Todo lo que viene de la marca está en reporte/recursos/marca/ (copia de globalaize-conocimiento/marca):
  * vidrio.py: el fondo de luces y los paneles de vidrio, el mismo de los tableros de Power BI;
  * fuentes/: IBM Plex Sans y Newsreader en ttf (SIL Open Font License), para matplotlib y PowerPoint;
  * logos/: el isotipo y el logo horizontal sobre fondo oscuro.

Reglas que se respetan (marca/README.md):
  * fondo #040F23 con luces solo cian y azul, panel de vidrio esmerilado, un solo nivel;
  * textos en tinta #F0EEE9, nunca del color de la serie;
  * series en el orden fijo cian, violeta, oliva, azul, rojo, verde azulado, magenta, verde; sin naranja;
  * rojo y verde de estado (#EF6661 / #62D286) solo para subas y bajas, y siempre con flecha o etiqueta.
"""

import functools
import importlib.util
import io
from contextlib import contextmanager
from pathlib import Path

import matplotlib as mpl
from matplotlib import font_manager
from PIL import Image

MARCA = Path(__file__).resolve().parent.parent / "recursos" / "marca"

# ── Colores (tema oscuro de Power BI de la marca) ────────────────────────────
PAGINA = "#040F23"
TARJETA = "#051E45"
ELEVADA = "#0D2C5F"
BORDE = "#2A394D"
TINTA = "#F0EEE9"
SECUNDARIO = "#BBC5D1"
TENUE = "#8D9AA8"

CIAN, VIOLETA, OLIVA, AZUL = "#0DA4CF", "#795EC9", "#A69722", "#4170CB"
ROJO, VERDE_AZULADO, MAGENTA, VERDE = "#C13234", "#3BAB8D", "#B33879", "#47AB4F"
SERIES = [CIAN, VIOLETA, OLIVA, AZUL, ROJO, VERDE_AZULADO, MAGENTA, VERDE]

# Estados: solo para subas, bajas y alertas
# Estados, en pastel (20/11/2026): subas, bajas y alertas, más tranquilos sobre el vidrio. Antes #62D286 y #EF6661
BUENO, MALO, NEUTRO = "#8FCFA8", "#E89A96", "#D8C65A"

# ── Tipografías ──────────────────────────────────────────────────────────────
# Matplotlib no lee woff2: se convierten a ttf una vez (ver preparar_fuentes).
# Las letras que la marca no trae (▲ ▼ Δ) caen a DejaVu Sans, que viene con matplotlib.
TEXTO = ["IBM Plex Sans", "DejaVu Sans"]
TITULO = ["Newsreader Medium", "DejaVu Serif"]
# Nombres de familia tal como los ve PowerPoint una vez instaladas las fuentes
PPT_TEXTO = "IBM Plex Sans"
PPT_TEXTO_LIGERO = "IBM Plex Sans Light"  # las cifras grandes: finas, con los dígitos de ancho fijo de Plex
PPT_TEXTO_MEDIO = "IBM Plex Sans Medium"
PPT_TEXTO_NEGRITA = "IBM Plex Sans SemiBold"
PPT_TITULO = "Newsreader"


_FUENTES_LISTAS = False


def registrar_fuentes() -> None:
    """Le avisa a matplotlib de los ttf de la marca (una sola vez por proceso)."""
    global _FUENTES_LISTAS
    if _FUENTES_LISTAS:
        return
    for ruta in sorted((MARCA / "fuentes").glob("*.ttf")):
        font_manager.fontManager.addfont(str(ruta))
    _FUENTES_LISTAS = True


@contextmanager
def contexto():
    """Estilo de partida de los gráficos de marca: los valores por defecto de matplotlib más el tema, sin estado global."""
    registrar_fuentes()
    with mpl.rc_context():
        mpl.rcdefaults()
        mpl.rcParams.update(tema_matplotlib())
        yield


def tema_matplotlib() -> dict:
    """rcParams de un gráfico sobre vidrio: fondo transparente, tinta clara, grilla apenas visible."""
    return {
        "figure.facecolor": "none", "axes.facecolor": "none", "savefig.facecolor": "none",
        "font.family": TEXTO, "font.size": 11, "text.color": TINTA,
        "axes.edgecolor": BORDE, "axes.labelcolor": SECUNDARIO, "axes.titlecolor": TINTA,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "grid.color": "#FFFFFF", "grid.alpha": 0.08, "grid.linewidth": 0.8,
        "xtick.color": SECUNDARIO, "ytick.color": SECUNDARIO,
        "xtick.major.size": 0, "ytick.major.size": 0, "xtick.labelsize": 10, "ytick.labelsize": 10,
        "legend.frameon": False, "legend.labelcolor": SECUNDARIO, "legend.fontsize": 10,
        "axes.prop_cycle": mpl.cycler(color=SERIES),
    }


# ── Vidrio ───────────────────────────────────────────────────────────────────

def _vidrio():
    """El módulo vidrio.py de la marca, cargado desde su repo."""
    ruta = MARCA / "vidrio.py"
    spec = importlib.util.spec_from_file_location("vidrio_globalaize", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    # El fondo de luces es el mismo para el mismo tamaño y es lo más lento de dibujar (un desenfoque enorme): se calcula una vez.
    # pagina() y panel() lo copian o lo recortan, nunca lo modifican.
    modulo.luces = functools.lru_cache(maxsize=16)(modulo.luces)
    return modulo


_VIDRIO = None


def vidrio():
    global _VIDRIO
    if _VIDRIO is None:
        _VIDRIO = _vidrio()
    return _VIDRIO


def fondo_con_paneles(ancho: int, alto: int, paneles: list[tuple[float, float, float, float]]) -> Image.Image:
    """Fondo de luces con un panel de vidrio en cada (x, y, ancho, alto), en píxeles lógicos.

    La imagen sale al doble de resolución (K = 2 en vidrio.py).
    """
    return vidrio().pagina(paneles, ancho, alto)


def logo(nombre: str = "globalaize-mark-dark-1024.png") -> Image.Image:
    return Image.open(MARCA / "logos" / nombre).convert("RGBA")


def tarjeta_de_grafico(png: bytes, ancho_final: int = 1400, relleno: int = 22, marca: bool = True) -> Image.Image:
    """Un gráfico transparente (PNG a 200 dpi) montado sobre su panel de vidrio, listo para el mail.

    El panel deja `relleno` píxeles lógicos de luces alrededor. Abajo a la derecha va el isotipo
    de GlobalAIze, chico y apagado.
    """
    grafico = Image.open(io.BytesIO(png)).convert("RGBA")
    k = vidrio().K
    gw, gh = grafico.width / k, grafico.height / k  # px lógicos
    ancho, alto = round(gw + 2 * relleno), round(gh + 2 * relleno)
    fondo = fondo_con_paneles(ancho, alto, [(relleno / 2, relleno / 2, ancho - relleno, alto - relleno)]).convert("RGBA")
    fondo.alpha_composite(grafico, (relleno * k, relleno * k))
    if marca:
        isotipo = logo()
        lado = 34 * k
        isotipo = isotipo.resize((round(isotipo.width * lado / isotipo.height), lado), Image.LANCZOS)
        isotipo.putalpha(isotipo.getchannel("A").point(lambda v: round(v * 0.55)))
        fondo.alpha_composite(isotipo, (fondo.width - isotipo.width - (relleno + 14) * k, fondo.height - lado - (relleno + 12) * k))
    fondo = fondo.convert("RGB")
    if fondo.width > ancho_final:
        fondo = fondo.resize((ancho_final, round(fondo.height * ancho_final / fondo.width)), Image.LANCZOS)
    return fondo
