"""Genera los íconos PNG de la presentación (reporte/recursos/) a partir de SVG, con Chromium.

PowerPoint no muestra bien los SVG en todas sus versiones, así que la presentación
usa PNG. Se corren una sola vez y quedan en el repo; volver a correrlo solo hace
falta para cambiar un ícono.

Uso: python iconos_presentacion.py

GlobalAIze tiene dos imágenes, las dos sacadas del repo del sitio (globalaize/):
- globalaize_logo.png (1024 px, fondo blanco): el logo completo, marca más nombre, de
  src/assets/brand/globalaize-logo.svg pasado a PNG con Chromium. Va en la portada del
  deck y en el encabezado del mail.
- globalaize.png: el ícono, la proa en blanco sobre el degradé azul marino del sitio, con
  la geometría de public/favicon.svg y las esquinas redondeadas como los demás íconos. Va
  donde el logo completo no se leería: la fila de links del deck y el pie del mail.
"""

import re
import sys
from pathlib import Path

DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(DIR))  # para importar construir.py, el del diagrama
DESTINO = DIR.parent.parent / "reporte" / "recursos"
LADO = 256


def _github() -> str:
    svg = (DIR / "iconos" / "si_github.svg").read_text(encoding="utf-8")
    camino = re.search(r'<path d="([^"]+)"', svg).group(1)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="-3 -3 30 30">'
        f'<circle cx="12" cy="12" r="15" fill="#24292E"/><path d="{camino}" fill="#FFFFFF"/></svg>'
    )


# La marca de GlobalAIze (la proa): los trazos de public/favicon.svg del sitio
MARCA_GLOBALAIZE = (
    '<rect x="126" y="23" width="3" height="18" rx="0.8"/><rect x="122" y="33.5" width="11" height="2.6" rx="0.8"/><rect x="110" y="39" width="35" height="3.4" rx="1"/><rect x="125.5" y="47" width="4" height="13.5" rx="1"/><rect x="125.5" y="65" width="4" height="3.5" rx="1"/><rect x="125.5" y="73" width="4" height="25.5" rx="1"/><rect x="114.5" y="46" width="3.4" height="27.5" rx="1"/><rect x="114.5" y="79" width="3.4" height="2.6" rx="1"/><rect x="114.5" y="87" width="3.4" height="13.5" rx="1"/><rect x="137.1" y="46" width="3.4" height="27.5" rx="1"/><rect x="137.1" y="79" width="3.4" height="2.6" rx="1"/><rect x="137.1" y="87" width="3.4" height="13.5" rx="1"/><rect x="100.5" y="51" width="8.5" height="5.6" rx="1.6"/><rect x="102.5" y="63" width="4" height="25" rx="1"/><rect x="102.5" y="92" width="4" height="12.5" rx="1"/><rect x="146" y="51" width="8.5" height="5.6" rx="1.6"/><rect x="148.5" y="63" width="4" height="25" rx="1"/><rect x="148.5" y="92" width="4" height="12.5" rx="1"/><rect x="92.3" y="71" width="3.6" height="37.5" rx="1"/><rect x="159.1" y="71" width="3.6" height="37.5" rx="1"/><rect x="81.5" y="83" width="4" height="29.5" rx="1"/><rect x="169.5" y="83" width="4" height="29.5" rx="1"/><rect x="70.5" y="93" width="4" height="3.6" rx="1"/><rect x="70.5" y="101" width="4" height="15.5" rx="1"/><rect x="180.5" y="93" width="4" height="3.6" rx="1"/><rect x="180.5" y="101" width="4" height="15.5" rx="1"/><path d="M127.5 101.5 L181.5 121.3 L181.5 124 L127.5 173.5 L73.5 124 L73.5 121.3 Z"/>'
)


def _icono_globalaize(fondo: str, trazo: str) -> str:
    """La marca sobre un cuadrado redondeado, como los demás íconos (el favicon del sitio usa un círculo)."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs>'
        '<linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#123466"/>'
        '<stop offset="1" stop-color="#051e45"/></linearGradient></defs>'
        f'<rect width="100" height="100" rx="18" fill="{fondo}"/>'
        f'<svg x="22" y="14" width="56" height="73" viewBox="68 20 119 156" fill="{trazo}">'
        f'{MARCA_GLOBALAIZE}</svg></svg>'
    )


ICONOS = {
    "github.png": _github(),
    "linkedin.png": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<rect width="100" height="100" rx="18" fill="#0A66C2"/>'
        '<text x="50" y="74" text-anchor="middle" font-family="Arial, sans-serif" font-weight="700" '
        'font-size="62" fill="#FFFFFF">in</text></svg>'
    ),
    # El ícono de GlobalAIze: la marca en blanco sobre el degradé azul marino del sitio, y la
    # variante clara (marca en azul sobre blanco) para las superficies oscuras del deck
    "globalaize.png": _icono_globalaize("url(#g)", "#FFFFFF"),
    "globalaize_claro.png": _icono_globalaize("#FFFFFF", "#051e45"),
    "bitcoin.png": (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">'
        '<circle cx="50" cy="50" r="48" fill="#F7931A"/><circle cx="50" cy="50" r="42" fill="none" '
        'stroke="#FFFFFF" stroke-opacity=".35" stroke-width="2"/>'
        '<text x="50" y="70" text-anchor="middle" font-family="Segoe UI Symbol, Segoe UI, Arial, sans-serif" '
        'font-weight="700" font-size="58" fill="#FFFFFF" transform="rotate(14 50 50)">₿</text></svg>'
    ),
}


# Las tecnologías del proyecto, para el pie de la portada: los mismos logos del diagrama
# de arquitectura (construir.py). Quedan en reporte/recursos/tecnologias/.
def _tecnologias() -> dict[str, str]:
    import construir as c

    return {
        "python": c.dev("python"), "playwright": c.dev("playwright"), "pandas": c.dev("pandas"),
        "pydantic": c.si("pydantic", "#E92063"), "sqlalchemy": c.dev("sqlalchemy"),
        "postgresql": c.dev("postgresql"), "supabase": c.dev("supabase"), "gemini": c.GEMINI,
        "matplotlib": c.dev("matplotlib"), "seaborn": c.SEABORN, "jinja": c.si("jinja", "#081E40"),
        "powerpoint": c.si("microsoftpowerpoint", "#B7472A"), "githubactions": c.dev("githubactions"),
        "cloudflare": c.dev("cloudflareworkers"), "pytest": c.dev("pytest"),
    }


def main() -> None:
    from playwright.sync_api import sync_playwright

    DESTINO.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        navegador = p.chromium.launch()
        try:
            pagina = navegador.new_page(viewport={"width": LADO, "height": LADO})
            for nombre, svg in ICONOS.items():
                svg = svg.replace("<svg ", f'<svg width="{LADO}" height="{LADO}" ', 1)
                pagina.set_content(f'<html><body style="margin:0;background:transparent">{svg}</body></html>')
                pagina.screenshot(path=str(DESTINO / nombre), omit_background=True,
                                  clip={"x": 0, "y": 0, "width": LADO, "height": LADO})
                print(nombre)
            carpeta = DESTINO / "tecnologias"
            carpeta.mkdir(exist_ok=True)
            for nombre, uri in _tecnologias().items():
                pagina.set_content(
                    f'<html><body style="margin:0;background:transparent"><img src="{uri}" '
                    f'style="width:{LADO}px;height:{LADO}px;object-fit:contain;display:block"></body></html>'
                )
                pagina.wait_for_timeout(50)
                pagina.screenshot(path=str(carpeta / f"{nombre}.png"), omit_background=True,
                                  clip={"x": 0, "y": 0, "width": LADO, "height": LADO})
                print("tecnologias/" + nombre)
        finally:
            navegador.close()


if __name__ == "__main__":
    main()
