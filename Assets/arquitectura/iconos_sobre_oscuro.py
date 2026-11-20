"""Los íconos de la presentación listos para ir directo sobre el vidrio azul, con sus colores y sin cuadradito detrás.

Casi todos los íconos de colores (reporte/recursos/ y reporte/recursos/tecnologias/) se ven bien sobre fondo oscuro. Unos
pocos tienen una parte muy oscura (el navy de Jinja, el negro de pandas, el círculo de GitHub...) que se pierde: ahí solo
se aclaran esos píxeles, conservando su tono. Lo demás queda tal cual.

Uso: python iconos_sobre_oscuro.py   (deja los PNG en reporte/recursos/oscuro/)
Se corre una sola vez y quedan en el repo; volver a correrlo solo hace falta si cambia un ícono de color.
"""

import colorsys
from pathlib import Path

from PIL import Image

RECURSOS = Path(__file__).resolve().parent.parent.parent / "reporte" / "recursos"
DESTINO = RECURSOS / "oscuro"
UMBRAL = 90  # luminancia (0 a 255) por debajo de la cual un píxel se considera "oscuro"
PARTE_OSCURA = 0.40  # un ícono se aclara si más de esta fracción de lo que dibuja es oscura
LUMINOSIDAD = {"github": 0.42}  # el círculo de GitHub no puede ser tan claro como el octocat blanco de adentro
LUMINOSIDAD_POR_DEFECTO = 0.74
NO_TOCAR = {"globalaize", "linkedin"}  # su fondo (azul marino de la marca, azul de LinkedIn) es de marca y se lee bien


def sobre_oscuro(origen: Path) -> Image.Image:
    imagen = Image.open(origen).convert("RGBA")
    pixeles = list(imagen.getdata())
    opacos = [p for p in pixeles if p[3] > 200]
    luz = lambda p: 0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2]  # noqa: E731
    if origen.stem in NO_TOCAR or not opacos or sum(luz(p) < UMBRAL for p in opacos) / len(opacos) < PARTE_OSCURA:
        return imagen
    objetivo = LUMINOSIDAD.get(origen.stem, LUMINOSIDAD_POR_DEFECTO)
    nuevos = []
    for r, g, b, a in pixeles:
        if a and luz((r, g, b)) < UMBRAL:
            h, _, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
            r, g, b = (round(c * 255) for c in colorsys.hls_to_rgb(h, objetivo, min(s, 0.55)))
        nuevos.append((r, g, b, a))
    salida = Image.new("RGBA", imagen.size)
    salida.putdata(nuevos)
    return salida


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    origenes = [p for p in RECURSOS.glob("*.png") if p.stem not in ("globalaize_logo", "globalaize_claro", "bitcoin")]
    origenes += list((RECURSOS / "tecnologias").glob("*.png"))
    for origen in sorted(origenes):
        sobre_oscuro(origen).save(DESTINO / origen.name, optimize=True)
        print(origen.name)


if __name__ == "__main__":
    main()
