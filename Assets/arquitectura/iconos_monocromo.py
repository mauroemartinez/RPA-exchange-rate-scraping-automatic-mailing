"""Versión monocromática de los íconos de la presentación: todo en la tinta de la marca (#F0EEE9) sobre transparente.

Los íconos de colores (reporte/recursos/ y reporte/recursos/tecnologias/) traen los colores de cada marca y
sobre el vidrio azul obligaban a ponerles un cuadradito blanco detrás. Acá cada ícono conserva su forma y su
detalle: lo claro queda en tinta plena y lo oscuro, más tenue (el alfa sigue a la luminancia), así que el
Python de dos colores se lee como dos tonos de la misma tinta y no como una mancha.

Uso: python iconos_monocromo.py   (deja los PNG en reporte/recursos/mono/)
Se corre una sola vez y quedan en el repo; volver a correrlo solo hace falta si cambia un ícono de color.
"""

from pathlib import Path

from PIL import Image, ImageChops

RECURSOS = Path(__file__).resolve().parent.parent.parent / "reporte" / "recursos"
DESTINO = RECURSOS / "mono"
TINTA = (0xF0, 0xEE, 0xE9)
PISO, TECHO = 0.34, 1.0  # el alfa de lo más oscuro y de lo más claro


def monocromo(origen: Path) -> Image.Image:
    """El ícono en tinta, con el alfa original modulado por la luminancia."""
    rgba = Image.open(origen).convert("RGBA")
    luz = rgba.convert("L")
    alfa = rgba.getchannel("A")
    # Se estira el contraste de la luminancia de ESE ícono: un logo todo oscuro no tiene que quedar apagado
    bajo, alto = luz.getextrema()
    escala = 1 / max(alto - bajo, 1)
    modulado = luz.point(lambda v: round(255 * (PISO + (TECHO - PISO) * (v - bajo) * escala)))
    nuevo = Image.new("RGBA", rgba.size, TINTA + (0,))
    nuevo.putalpha(ImageChops.multiply(alfa, modulado))  # el alfa original (bordes suaves) por la modulación
    return nuevo


def main() -> None:
    DESTINO.mkdir(parents=True, exist_ok=True)
    origenes = [p for p in RECURSOS.glob("*.png") if p.stem not in ("globalaize_logo", "globalaize_claro", "bitcoin")]
    origenes += list((RECURSOS / "tecnologias").glob("*.png"))
    for origen in sorted(origenes):
        monocromo(origen).save(DESTINO / origen.name, optimize=True)
        print(origen.name)


if __name__ == "__main__":
    main()
