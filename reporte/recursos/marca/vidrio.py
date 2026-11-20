"""Estética de vidrio de GlobalAIze (glassmorphism) para tableros de Power BI y piezas visuales.

Power BI solo pinta fondos de un color liso: no desenfoca lo que hay detrás ni hace degradés o bordes de luz.
El vidrio se dibuja como imagen de fondo de la página y los visuales van encima, transparentes:

  * luces de la marca (cian y azul, nunca violeta ni naranja) muy difuminadas sobre el azul oscuro de la página;
  * en el lugar de cada tarjeta, un panel esmerilado: la luz de atrás desenfocada, teñida con el azul de la marca;
  * un canto de luz suave en todo el borde, un poco más claro en dos esquinas opuestas, y una sombra que lo despega.

Uso:
    python vidrio.py fondo.png "20,12,1240,68;20,92,800,302;832,92,428,302"
    python vidrio.py fondo.png "<rects>" --lienzo 1280x720

Los rectángulos son x,y,ancho,alto en píxeles del lienzo (la posición de cada visual: panel Formato > General >
Propiedades, o el visual.json del PBIP). En Power BI: Formato de página > Fondo del lienzo > Imagen, escala
"Ajustar", transparencia 0; y a cada visual se le apagan el fondo, el borde y la sombra. La imagen sale al doble
de resolución. Si un visual se mueve, se vuelve a generar el fondo.

Requiere Pillow (pip install pillow). También se puede importar: pagina(rects) devuelve la imagen.
"""
import argparse

from PIL import Image, ImageChops, ImageDraw, ImageFilter

K = 2                                  # escala de dibujo
TINTE = 0.70                           # cuánto del azul de la marca cubre la luz de atrás: más tinte, panel más oscuro hacia el centro
BRILLO = 0.0                           # reflejos del panel (velo blanco de arriba, franja diagonal, resplandor interno): 0 = mate, 1 = como el original
CANTO = 0.55                           # intensidad del borde de luz, 1 = como el original
LUCES_FUERZA = 0.24                    # intensidad de las luces del fondo (0 = azul liso, 1 = luces a pleno): menos, degradé más suave
PAGINA = (4, 15, 35)                   # #040F23
MARCA = (5, 30, 69)                    # #051E45, tinte del esmerilado
CIAN, AZUL, AZUL_PROFUNDO = (34, 181, 225), (31, 79, 168), (16, 52, 140)
LUCES = ((0.20, 0.38, 0.17, 0.30, CIAN), (0.82, 0.78, 0.17, 0.30, AZUL), (0.52, 0.10, 0.20, 0.18, AZUL_PROFUNDO))


def luces(w, h, k=K):
    """Fondo: el azul oscuro de la página con tres manchas de luz de la marca, muy difuminadas."""
    W, H = round(w * k), round(h * k)
    capa = Image.new('RGB', (W, H), PAGINA)
    d = ImageDraw.Draw(capa)
    for cx, cy, rx, ry, col in LUCES:
        d.ellipse(((cx - rx) * W, (cy - ry) * H, (cx + rx) * W, (cy + ry) * H), fill=col)
    capa = capa.filter(ImageFilter.GaussianBlur(110 * k))
    return Image.blend(Image.new('RGB', (W, H), PAGINA), capa, LUCES_FUERZA)


def _mascara(W, H, r):
    m = Image.new('L', (W, H), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, W - 1, H - 1), r, fill=255)
    return m


def _canto(W, H, r, grosor, k):
    """Borde de luz en todo el contorno, más claro arriba a la izquierda y abajo a la derecha."""
    aro = Image.new('L', (W, H), 0)
    ImageDraw.Draw(aro).rounded_rectangle((0, 0, W - 1, H - 1), r, outline=255, width=grosor)
    aro = aro.filter(ImageFilter.GaussianBlur(0.6 * k))
    g = Image.linear_gradient('L').resize((W, H))
    gx = Image.linear_gradient('L').rotate(90, expand=True).resize((W, H)).transpose(Image.FLIP_LEFT_RIGHT)
    diag = ImageChops.add(g, gx, scale=2.0)
    picos = diag.point(lambda v: round(CANTO * (45 + 95 * (abs(v - 127.5) / 127.5) ** 1.3)))
    return ImageChops.multiply(aro, picos)


def panel(fondo, luz, x, y, w, h, r=14, k=K):
    """Dibuja un panel de vidrio sobre fondo. luz es el fondo de luces sin paneles: lo que se ve esmerilado."""
    X, Y, W, H, R = round(x * k), round(y * k), round(w * k), round(h * k), r * k
    sombra = Image.new('L', fondo.size, 0)
    ImageDraw.Draw(sombra).rounded_rectangle((X, Y + 8 * k, X + W, Y + H + 8 * k), R, fill=120)
    sombra = sombra.filter(ImageFilter.GaussianBlur(16 * k))
    fondo = Image.composite(Image.new('RGB', fondo.size, (1, 6, 16)), fondo, sombra)
    detras = luz.crop((X, Y, X + W, Y + H)).filter(ImageFilter.GaussianBlur(36 * k))
    vidrio = Image.blend(detras, Image.new('RGB', (W, H), MARCA), TINTE)
    vidrio = Image.blend(vidrio, Image.new('RGB', (W, H), (255, 255, 255)), 0.04 * BRILLO).convert('RGBA')
    velo = Image.new('L', (W, H), 0)
    dv = ImageDraw.Draw(velo)
    for yy in range(min(H, 50 * k)):
        dv.line((0, yy, W, yy), fill=round(10 * BRILLO * (1 - yy / (50 * k)) ** 2))
    a = min(W, 700 * k)
    dv.polygon([(a * .08, 0), (a * .30, 0), (a * .14, H), (-a * .08, H)], fill=round(7 * BRILLO))
    velo = velo.filter(ImageFilter.GaussianBlur(14 * k))
    vidrio = Image.composite(Image.new('RGBA', (W, H), (255, 255, 255, 255)), vidrio, velo)
    interno = Image.new('L', (W, H), 0)
    ImageDraw.Draw(interno).rounded_rectangle((0, 0, W - 1, H - 1), R, outline=round(30 * BRILLO), width=8 * k)
    interno = interno.filter(ImageFilter.GaussianBlur(7 * k))
    vidrio = Image.composite(Image.new('RGBA', (W, H), (170, 215, 255, 255)), vidrio, interno)
    vidrio = Image.composite(Image.new('RGBA', (W, H), (235, 245, 255, 255)), vidrio, _canto(W, H, R, round(1.5 * k), k))
    fondo.paste(vidrio.convert('RGB'), (X, Y), _mascara(W, H, R))
    return fondo


def pagina(rects, w=1280, h=720, k=K):
    """Fondo de página con luces y un panel de vidrio en cada rectángulo (x, y, ancho, alto)."""
    luz = luces(w, h, k)
    fondo = luz.copy()
    for x, y, ww, hh in rects:
        fondo = panel(fondo, luz, x, y, ww, hh, k=k)
    return fondo


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('salida')
    ap.add_argument('rects', help='"x,y,ancho,alto;x,y,ancho,alto;..."')
    ap.add_argument('--lienzo', default='1280x720', help='tamaño del lienzo, por defecto 1280x720')
    a = ap.parse_args()
    w, h = (int(v) for v in a.lienzo.lower().split('x'))
    rects = [tuple(float(v) for v in r.split(',')) for r in a.rects.split(';') if r.strip()]
    pagina(rects, w, h).save(a.salida, optimize=True)
    print('listo:', a.salida)


if __name__ == '__main__':
    main()
