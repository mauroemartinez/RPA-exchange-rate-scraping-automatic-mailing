"""La presentación ejecutiva con la estética de GlobalAIze: nueve diapositivas sobre vidrio azul.

Mismas nueve diapositivas, datos y textos que describe reporte/presentacion.py (de ahí se
importan las frases calculadas y los helpers de datos). Lo visual es de este módulo:

  * cada diapositiva es una imagen de fondo con las luces de la marca y un panel de vidrio
    en el lugar de cada tarjeta (vidrio.py, como en los tableros de Power BI); los gráficos
    y los textos van encima, sin relleno, como piden las reglas de la marca;
  * los cinco gráficos nativos siguen siendo editables, ahora con la paleta de la marca;
  * títulos en Newsreader y textos en IBM Plex Sans: hay que tener instaladas las fuentes
    (están en reporte/recursos/marca/fuentes/), PowerPoint no las incrusta;
  * rojo y verde solo para subas y bajas, siempre con flecha.
"""

import io
import logging
import os
from datetime import date
from pathlib import Path

import pandas as pd
from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

from reporte import charts, email_report, ia_generator, indicadores, presentacion, transformations
from reporte.marca import animaciones, estilo, graficos, nativos

log = logging.getLogger(__name__)

PX = 9525  # EMU por píxel: el lienzo es de 1280 x 720, 96 px por pulgada
ANCHO, ALTO = 1280, 720
ARCHIVO = presentacion.ARCHIVO
ANIMAR = True  # transición entre diapositivas y entrada animada de gráficos y textos
NOMBRE_FONDO, NOMBRE_ISOTIPO = "Fondo de vidrio", "Isotipo GlobalAIze"


def _rgb(hexa: str) -> RGBColor:
    return RGBColor.from_string(hexa.lstrip("#").upper())


TINTA, SECUNDARIO, TENUE = _rgb(estilo.TINTA), _rgb(estilo.SECUNDARIO), _rgb(estilo.TENUE)
CIAN, BUENO, MALO = _rgb(estilo.CIAN), _rgb(estilo.BUENO), _rgb(estilo.MALO)


def _e(valor: float) -> Emu:
    return Emu(round(valor * PX))


class Diapositiva:
    """Una diapositiva en blanco con su lista de paneles de vidrio, que se dibujan al final como imagen de fondo."""

    def __init__(self, prs: Presentation):
        self.slide = prs.slides.add_slide(prs.slide_layouts[6])
        self.paneles: list[tuple[float, float, float, float]] = []
        self.animables: list[tuple] = []  # (forma, "fade" | "wipe"), en el orden en que entran

    def panel(self, x, y, ancho, alto):
        self.paneles.append((x, y, ancho, alto))
        return x, y, ancho, alto

    def cerrar(self) -> None:
        """Pone el fondo de luces y vidrio detrás de todo lo demás."""
        fondo = estilo.fondo_con_paneles(ANCHO, ALTO, self.paneles).convert("RGB")
        buffer = io.BytesIO()
        fondo.save(buffer, format="JPEG", quality=90, optimize=True)
        buffer.seek(0)
        imagen = self.slide.shapes.add_picture(buffer, 0, 0, _e(ANCHO), _e(ALTO))
        imagen.name = NOMBRE_FONDO
        arbol = self.slide.shapes._spTree
        arbol.remove(imagen._element)
        arbol.insert(2, imagen._element)  # después de nvGrpSpPr y grpSpPr: primero en el orden de dibujo
        if ANIMAR:
            animaciones.transicion(self.slide)
            animaciones.entradas(self.slide, self.animables)

    # ── texto ────────────────────────────────────────────────────────────────
    def texto(self, x, y, ancho, alto, texto, tamanio=14, color=TINTA, fuente=estilo.PPT_TEXTO, alinear=PP_ALIGN.LEFT,
              ancla=MSO_ANCHOR.TOP, link: str | None = None, espaciado: float | None = None, animar: str | None = None):
        caja = self.slide.shapes.add_textbox(_e(x), _e(y), _e(ancho), _e(alto))
        marco = caja.text_frame
        marco.word_wrap = True
        marco.vertical_anchor = ancla
        marco.margin_left = marco.margin_right = marco.margin_top = marco.margin_bottom = 0
        for i, linea in enumerate(texto.split("\n")):
            parrafo = marco.paragraphs[0] if i == 0 else marco.add_paragraph()
            parrafo.alignment = alinear
            run = parrafo.add_run()
            run.text = linea
            run.font.size, run.font.name, run.font.color.rgb = Pt(tamanio), fuente, color
            if espaciado is not None:
                run.font._element.set("spc", str(int(espaciado * 100)))
        if link:
            caja.click_action.hyperlink.address = link
        if animar:
            self.animables.append((caja, animar))
        return caja

    def bloques(self, x, y, ancho, alto, bloques, maximo: int = 16, minimo: int = 10, color=SECUNDARIO, tamanio: int | None = None):
        """Secciones [(título, texto)] dentro de la caja, con la letra más grande que entre. Sin texto no dibuja nada."""
        bloques = [(t, tx) for t, tx in bloques if tx]
        if not bloques:
            return None
        tamanio = tamanio or _tamanio(bloques, ancho, alto, maximo, minimo)
        caja = self.slide.shapes.add_textbox(_e(x), _e(y), _e(ancho), _e(alto))
        marco = caja.text_frame
        marco.word_wrap = True
        marco.margin_left = marco.margin_right = marco.margin_top = marco.margin_bottom = 0
        primero = True
        for titulo, texto in bloques:
            p = marco.paragraphs[0] if primero else marco.add_paragraph()
            if not primero:
                p.space_before = Pt(14)
            primero = False
            p.space_after = Pt(5)
            if titulo:
                run = p.add_run()
                run.text = titulo.upper()
                run.font.size, run.font.name, run.font.color.rgb = Pt(max(tamanio - 3, 9)), estilo.PPT_TEXTO_NEGRITA, CIAN
                run.font._element.set("spc", "100")
            for k, linea in enumerate(texto.split("\n")):
                # Sin título, el primer renglón usa el párrafo que ya está abierto
                p = p if (not titulo and k == 0) else marco.add_paragraph()
                p.space_after = Pt(6)
                run = p.add_run()
                run.text = linea
                run.font.size, run.font.name, run.font.color.rgb = Pt(tamanio), estilo.PPT_TEXTO, color
        self.animables.append((caja, "fade"))
        return caja

    def imagen(self, origen, x, y, ancho, alto, margen: float = 12, animar: str | None = "wipe"):
        """La imagen lo más grande posible dentro de la caja, centrada y sin deformarla."""
        enmemoria = isinstance(origen, io.BytesIO)
        with Image.open(origen) as im:
            w, h = im.size
        if enmemoria:
            origen.seek(0)
        escala = min((ancho - 2 * margen) / w, (alto - 2 * margen) / h)
        iw, ih = w * escala, h * escala
        imagen = self.slide.shapes.add_picture(origen if enmemoria else str(origen), _e(x + (ancho - iw) / 2),
                                               _e(y + (alto - ih) / 2), _e(iw), _e(ih))
        if animar:
            self.animables.append((imagen, animar))
        return imagen

    def icono(self, archivo: Path, x, y, lado, link: str | None = None):
        """El ícono con sus colores directo sobre el vidrio, sin cuadradito detrás (los muy oscuros ya vienen aclarados)."""
        ruta = presentacion.RECURSOS / "oscuro" / Path(archivo).name
        imagen = self.slide.shapes.add_picture(str(ruta), _e(x), _e(y), _e(lado), _e(lado))
        if link:
            imagen.click_action.hyperlink.address = link
        return imagen

    def linea(self, x, y, ancho, color=CIAN, grosor: float = 2.5):
        """Un trazo fino de acento (una regla corta bajo un rótulo)."""
        forma = self.slide.shapes.add_shape(1, _e(x), _e(y), _e(ancho), _e(grosor))
        forma.fill.solid()
        forma.fill.fore_color.rgb = color
        forma.line.fill.background()
        forma.shadow.inherit = False

    def grafico(self, x, y, ancho, alto, titulo: str, subtitulo: str | None, dibujar, imagen: Path | None = None) -> None:
        """Un gráfico nativo con su título adentro de la tarjeta; si no se puede armar, la imagen; si no hay, el aviso."""
        self.texto(x + 22, y + 14, ancho - 44, 26, titulo, 16, TINTA, estilo.PPT_TITULO)
        alto_cabecera = 46
        if subtitulo:
            self.texto(x + 22, y + 40, ancho - 44, 18, subtitulo, 10.5, TENUE)
            alto_cabecera = 64
        caja = (x + 10, y + alto_cabecera, ancho - 20, alto - alto_cabecera - 10)
        if dibujar is not None:
            antes = len(self.slide.shapes)
            try:
                dibujar(self.slide, *(_e(v) for v in caja))
                self.animables.extend((f, "wipe") for f in list(self.slide.shapes)[antes:] if f.has_chart)
                return
            except Exception:
                log.exception("No se pudo armar un gráfico nativo; va la imagen")
                for forma in list(self.slide.shapes)[antes:]:
                    rid = forma._element.chart_rId if forma.has_chart else None
                    forma._element.getparent().remove(forma._element)
                    if rid:
                        self.slide.part.drop_rel(rid)
        if imagen is not None:
            self.imagen(imagen, *caja)
        else:
            self.texto(x + 20, y + alto / 2 - 12, ancho - 40, 24, "Gráfico no disponible para este día.", 16, TENUE)


def _tamanio(bloques, ancho: float, alto: float, maximo: int, minimo: int) -> int:
    """El tamaño de letra más grande con el que entran las secciones. IBM Plex Sans ocupa unas 0,56 veces su tamaño por letra."""
    ancho_pt, alto_pt = ancho * 0.75, alto * 0.75
    for tamanio in range(maximo, minimo - 1, -1):
        por_renglon = max(1, int(ancho_pt / (tamanio * 0.56)))
        total = 0.0
        for i, (_, texto) in enumerate(bloques):
            total += (14 if i else 0) + (tamanio - 2) * 1.25 + 5
            for linea in texto.split("\n"):
                total += -(-max(len(linea), 1) // por_renglon) * tamanio * 1.3 + 6
        if total <= alto_pt:
            return tamanio
    return minimo


# ── Piezas comunes ───────────────────────────────────────────────────────────

def _encabezado(prs: Presentation, titulo: str, fecha: date, numero: int, kicker: str | None = None) -> Diapositiva:
    d = Diapositiva(prs)
    d.panel(24, 16, 1232, 62)
    isotipo = estilo.logo()
    lado = 40
    buffer = io.BytesIO()
    isotipo.save(buffer, format="PNG")
    buffer.seek(0)
    d.slide.shapes.add_picture(buffer, _e(46), _e(27), _e(lado * isotipo.width / isotipo.height), _e(lado)).name = NOMBRE_ISOTIPO
    d.texto(104, 16, 800, 62, titulo, 28, TINTA, estilo.PPT_TITULO, ancla=MSO_ANCHOR.MIDDLE)
    if kicker:
        d.texto(700, 16, 380, 62, kicker.upper(), 10, CIAN, estilo.PPT_TEXTO_NEGRITA, PP_ALIGN.RIGHT, MSO_ANCHOR.MIDDLE, espaciado=1)
    d.texto(1090, 16, 146, 62, f"{fecha:%d/%m/%Y}", 15, SECUNDARIO, estilo.PPT_TEXTO_MEDIO, PP_ALIGN.RIGHT, MSO_ANCHOR.MIDDLE)
    d.texto(26, 696, 800, 16, "Reporte Macroeconómico · Mauro E. Martinez · GlobalAIze", 9.5, TENUE)
    d.texto(1180, 696, 76, 16, str(numero), 9.5, TENUE, alinear=PP_ALIGN.RIGHT)
    return d


def _variacion(hoy: float, ayer: float, decimales: int = 2) -> tuple[str, RGBColor]:
    """Variación contra la rueda anterior con flecha: subir es rojo y bajar, verde (criterio macro del mail)."""
    var = (hoy / ayer - 1) * 100
    if round(var, decimales) == 0:
        return "= sin cambios contra la rueda anterior", SECUNDARIO
    flecha = "▲" if var > 0 else "▼"
    return f"{flecha} {presentacion._signo(var)}% contra la rueda anterior", (MALO if var > 0 else BUENO)


def _kpi(d: Diapositiva, x, y, ancho, alto, titulo: str, valor: str, detalle: str, color) -> None:
    d.panel(x, y, ancho, alto)
    d.texto(x + 26, y + 22, ancho - 52, 18, titulo.upper(), 11.5, SECUNDARIO, estilo.PPT_TEXTO_NEGRITA, espaciado=1)
    d.texto(x + 26, y + 52, ancho - 52, 64, valor, 40, TINTA, estilo.PPT_TEXTO_MEDIO, animar="fade")
    d.texto(x + 26, y + alto - 44, ancho - 52, 24, detalle, 13, color, estilo.PPT_TEXTO_MEDIO)


def armar(df, imagenes: dict[str, Path], salida: Path, parrafo: str | None = None, comentarios: dict | None = None,
          explicaciones: dict | None = None, inflacion=None, btc=None) -> Path:
    """Arma la presentación en `salida`/ARCHIVO y devuelve su ruta.

    `df` es Fact_Mercado_Macro, más nuevo primero (la fila 0 es el día del reporte). `imagenes` son los
    gráficos del mail por nombre (charts.ORDEN_EN_MAIL): sirven de respaldo si un gráfico nativo falla y
    son los de BTC; el que falte sale como "Gráfico no disponible". `parrafo`, `comentarios` y
    `explicaciones` son los textos de esta corrida; sin ellos se leen de la fila 0 o van los fijos.
    `inflacion` (transformations.serie_inflacion) y `btc` (charts.preparar_btc) son para los gráficos
    nativos de inflación y para las frases de esa diapositiva.
    """
    hoy, ayer = df.iloc[0], df.iloc[1]
    fecha = presentacion._fecha(hoy["Fecha"])
    fwd_oficial, fwd_blue = transformations.forwards_fisher(df)
    resumen = email_report.resumen_ejecutivo(transformations.agregar_brechas_y_variaciones(df))
    if comentarios is None:
        comentarios = ia_generator.comentarios_por_grafico(hoy.get("ai_secciones"))
    if parrafo is None:
        guardado = hoy.get("ai_paragraph")
        parrafo = guardado if isinstance(guardado, str) and guardado else presentacion.SIN_ANALISIS
    if explicaciones is None:
        explicaciones = indicadores.explicaciones({})
    num, signo = presentacion._num, presentacion._signo
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)

    # Agregados y deuda van como imagen: la versión de la diapositiva (sin título y de otro tamaño) se redibuja
    # en memoria con los datos de esta corrida; si no se registró, va la imagen del mail
    transparentes: dict[str, io.BytesIO | Path] = {}
    for nombre in (charts.AGREGADOS, charts.DEUDA):
        if nombre not in imagenes:
            continue
        try:
            datos = graficos.png_para_diapositiva(nombre)
        except Exception:
            log.exception("No se pudo redibujar %s para la presentación; va la imagen del mail", nombre)
            datos = None
        transparentes[nombre] = io.BytesIO(datos) if datos else imagenes[nombre]

    prs = Presentation()
    prs.slide_width, prs.slide_height = _e(ANCHO), _e(ALTO)
    presentacion._metadatos(prs, fecha)
    numero = iter(range(2, 100))
    espacio = 16

    # 1. Portada ──────────────────────────────────────────────────────────────
    p = Diapositiva(prs)
    p.panel(48, 40, 1184, 640)
    logo = estilo.MARCA / "logos" / "globalaize-logo-horizontal-es-dark-1024.png"
    portada_logo = p.slide.shapes.add_picture(str(logo), _e(470), _e(78), _e(340), _e(340 * 305 / 1024))
    portada_logo.click_action.hyperlink.address = "https://www.globalaize.com"  # el logo grande es el link al sitio
    centro = {"alinear": PP_ALIGN.CENTER}
    p.texto(48, 196, 1184, 20, "ARGENTINA · INFORME DIARIO", 13, CIAN, estilo.PPT_TEXTO_NEGRITA, espaciado=3, **centro)
    p.texto(48, 224, 1184, 80, "Reporte Macroeconómico", 58, TINTA, estilo.PPT_TITULO, **centro)
    p.texto(48, 312, 1184, 28, "Dólar · Riesgo país · Tasas · Inflación · Agregados monetarios · Deuda · Bitcoin", 17, SECUNDARIO, **centro)
    p.texto(48, 360, 1184, 36, f"{fecha:%d/%m/%Y}", 24, TINTA, estilo.PPT_TEXTO_MEDIO, **centro)
    p.texto(48, 400, 1184, 24, "por Mauro E. Martinez · GlobalAIze", 14, TENUE, **centro)
    enlaces = [e for e in presentacion.LINKS if e[1] != "GlobalAIze"]
    lado, sep = 56, 170
    inicio = (ANCHO - sep * len(enlaces)) / 2
    for i, (icono, rotulo, url) in enumerate(enlaces):
        izq = inicio + i * sep
        p.icono(icono, izq + (sep - lado) / 2, 440, lado, url)
        p.texto(izq, 502, sep, 16, rotulo, 10.5, SECUNDARIO, alinear=PP_ALIGN.CENTER, link=url)
    p.linea(140, 548, 1000, _rgb("2A394D"), 1)
    p.texto(48, 548, 1184, 16, "STACK", 9.5, TENUE, estilo.PPT_TEXTO_NEGRITA, espaciado=2, **centro)
    cada, lado_tec = 70, 44
    inicio = (ANCHO - cada * len(presentacion.TECNOLOGIAS)) / 2
    for i, (archivo, rotulo) in enumerate(presentacion.TECNOLOGIAS):
        izq = inicio + i * cada
        p.icono(f"{archivo}.png", izq + (cada - lado_tec) / 2, 578, lado_tec)
        p.texto(izq - 4, 622, cada + 8, 14, rotulo, 8.5, SECUNDARIO, alinear=PP_ALIGN.CENTER)
    p.cerrar()

    # 2. Tablero ──────────────────────────────────────────────────────────────
    d = _encabezado(prs, "Tablero del día", fecha, next(numero), "Indicadores clave")
    def sube(a, b):
        return MALO if a > b else BUENO if a < b else SECUNDARIO
    tarjetas = [
        ("Dólar blue", f"$ {num(hoy['TCV_Blue'])}", *_variacion(hoy["TCV_Blue"], ayer["TCV_Blue"])),
        ("Dólar MEP", f"$ {num(hoy['TCV_MEP'])}", *_variacion(hoy["TCV_MEP"], ayer["TCV_MEP"])),
        ("Billete BNA", f"$ {num(hoy['TCV_Billete'])}", *_variacion(hoy["TCV_Billete"], ayer["TCV_Billete"])),
        ("Riesgo país", f"{num(hoy['riesgo_pais'], 0)} pts",
         f"{'▲' if hoy['riesgo_pais'] > ayer['riesgo_pais'] else '▼' if hoy['riesgo_pais'] < ayer['riesgo_pais'] else '='} "
         f"{signo(hoy['riesgo_pais'] - ayer['riesgo_pais'], 0)} pts contra la rueda anterior", sube(hoy["riesgo_pais"], ayer["riesgo_pais"])),
        ("BADLAR (TEA)", f"{num(hoy['bcra_tea'])}%", f"FED (EFFR): {num(hoy['fed_tea'])}%", SECUNDARIO),
        ("Forward oficial 3 meses", f"$ {num(fwd_oficial)}", f"Forward blue: $ {num(fwd_blue)}", SECUNDARIO),
    ]
    ancho_k = (1232 - 2 * espacio) / 3
    for i, (titulo, valor, detalle, color) in enumerate(tarjetas):
        _kpi(d, 24 + (i % 3) * (ancho_k + espacio), 92 + (i // 3) * (186 + espacio), ancho_k, 186, titulo, valor, detalle, color)
    diferencia = abs(resumen["ahorro_valor"])
    sentido = "más barato" if resumen["ahorro_valor"] > 0 else "más caro"
    d.panel(24, 92 + 2 * (186 + espacio), 1232, 684 - (92 + 2 * (186 + espacio)))
    d.bloques(52, 92 + 2 * (186 + espacio) + 24, 1176, 684 - (92 + 2 * (186 + espacio)) - 48, [
        ("Contra el blue", f"Comprar USD {resumen['cantidad_usd']} al oficial con impuestos (solidario) sale $ {num(diferencia)} {sentido} "
                           f"que en el blue: el solidario está {num(abs(resumen['brecha_solidario']))}% "
                           f"{'por debajo' if resumen['brecha_solidario'] > 0 else 'por encima'} del blue."),
        ("Cómo leerlo", "Verde y ▼: bajó contra la rueda anterior. Rojo y ▲: subió. Desde la macro, que el dólar y el riesgo país bajen es la buena noticia."),
    ], maximo=14)
    d.cerrar()

    # 3. Tipos de cambio ──────────────────────────────────────────────────────
    d = _encabezado(prs, "Tipos de cambio", fecha, next(numero), "Paralelas y oficiales")
    d.panel(24, 92, 1232, 120)
    d.texto(52, 108, 400, 16, "ANÁLISIS IA DEL DÍA", 11, CIAN, estilo.PPT_TEXTO_NEGRITA, espaciado=1)
    d.bloques(52, 130, 1176, 72, [("", parrafo)], maximo=16, minimo=10, color=TINTA)
    d.slide.notes_slide.notes_text_frame.text = parrafo
    mitad = (1232 - espacio) / 2
    frases = {"paralela": presentacion.frase_paralelas(hoy, ayer), "oficial": presentacion.frase_oficiales(hoy, ayer)}
    textos_cambio = [presentacion._comentario(comentarios, charts.cid(charts.TIPOS_DE_CAMBIO), c) or f
                     for c, f in frases.items()]
    comun = min(_tamanio([("x", t)], mitad - 52, 148, 14, 10) for t in textos_cambio)
    for j, (dibujar, clave, titulo, sub, frase) in enumerate([
        (nativos.paralelas, "paralela", "Cotizaciones paralelas", "Pesos por dólar. Punteado: compra.", frases["paralela"]),
        (nativos.oficiales, "oficial", "Cotizaciones oficiales (BNA)", "Pesos por dólar. Punteado: compra.", frases["oficial"]),
    ]):
        x = 24 + j * (mitad + espacio)
        d.panel(x, 228, mitad, 252)
        d.grafico(x, 228, mitad, 252, titulo, sub, lambda s, *caja, f=dibujar: f(s, *caja, df), imagenes.get(charts.TIPOS_DE_CAMBIO))
        d.panel(x, 496, mitad, 188)
        texto = presentacion._comentario(comentarios, charts.cid(charts.TIPOS_DE_CAMBIO), clave)
        d.bloques(x + 26, 516, mitad - 52, 148, [("Análisis IA" if texto else "Resumen del día", texto or frase)], tamanio=comun)
    d.cerrar()

    # 4. Riesgo país ──────────────────────────────────────────────────────────
    d = _encabezado(prs, "Riesgo país", fecha, next(numero), "Puntos básicos")
    d.panel(24, 92, 830, 592)
    d.grafico(24, 92, 830, 592, "Últimas 25 ruedas", "Rojo: el máximo de la ventana. Verde: el mínimo. Más bajo es mejor.",
              lambda s, *caja: nativos.riesgo_pais(s, *caja, df), imagenes.get(charts.RIESGO_PAIS))
    d.panel(870, 92, 386, 592)
    d.bloques(896, 116, 334, 544, [("Resumen del día", presentacion.frase_riesgo(df)),
                                    ("Análisis IA", presentacion._comentario(comentarios, charts.cid(charts.RIESGO_PAIS), "riesgo"))])
    d.cerrar()

    # 5. Inflación y variaciones ──────────────────────────────────────────────
    d = _encabezado(prs, "Inflación y variaciones acumuladas", fecha, next(numero), "Dólar contra precios")
    hay = inflacion is not None and not inflacion.empty
    for j, (nombre, titulo, sub, dibujar) in enumerate([
        (charts.INFLACION, "Inflación de los últimos 12 meses", "Barras: mensual. Línea: interanual (eje derecho).",
         lambda s, *caja: nativos.inflacion(s, *caja, inflacion)),
        (charts.VARIACIONES, "Dólar contra inflación", f"Variación acumulada desde {indicadores.mes_y_anio(pd.Timestamp(charts.FECHA_INICIO_VARIACIONES))}.",
         lambda s, *caja: nativos.variaciones(s, *caja, df, inflacion)),
    ]):
        x = 24 + j * (mitad + espacio)
        d.panel(x, 92, mitad, 392)
        d.grafico(x, 92, mitad, 392, titulo, sub, dibujar if hay else None, imagenes.get(nombre))
    frase = presentacion.frase_inflacion(inflacion, df)
    if frase:
        d.panel(24, 500, 1232, 184)
        d.bloques(52, 520, 1176, 144, [("Resumen del día", frase)], maximo=15)
    d.cerrar()

    # 6 y 7. Agregados y deuda ────────────────────────────────────────────────
    for titulo, kicker, nombre, cid in [("Agregados monetarios", "Dinero en circulación", charts.AGREGADOS, indicadores.CID_AGREGADOS),
                                         ("Endeudamiento, en dólares", "Tesoro, bancos y BCRA", charts.DEUDA, indicadores.CID_DEUDA)]:
        d = _encabezado(prs, titulo, fecha, next(numero), kicker)
        d.panel(24, 92, 700, 592)
        if nombre in transparentes:
            d.imagen(transparentes[nombre], 24, 92, 700, 592, margen=14)
        else:
            d.texto(48, 360, 650, 24, "Gráfico no disponible para este día.", 16, TENUE)
        d.panel(740, 92, 516, 592)
        explicacion = explicaciones.get(cid)
        if explicacion:
            parrafos = explicacion["texto"].split("\n")
            ideal = parrafos[-1].removeprefix("¿Qué sería lo ideal?").strip()
            d.bloques(768, 116, 460, 544, [("Resumen del día", explicacion["dato"]), ("¿Qué sería lo ideal?", ideal)])
            d.slide.notes_slide.notes_text_frame.text = "\n\n".join(filter(None, [*parrafos, explicacion["dato"]]))
        d.cerrar()

    # 8. Bitcoin ──────────────────────────────────────────────────────────────
    d = _encabezado(prs, "Bitcoin", fecha, next(numero), "BTC/USD")
    d.panel(24, 92, 860, 592)
    if charts.BTC in imagenes:
        d.imagen(imagenes[charts.BTC], 24, 92, 860, 592, margen=16)
    else:
        d.texto(48, 360, 800, 24, "Gráfico no disponible para este día.", 16, TENUE)
    d.panel(900, 92, 356, 592)
    d.bloques(926, 116, 304, 544, [("Resumen del día", presentacion.frase_btc(btc)),
                                    ("Análisis IA", presentacion._comentario(comentarios, charts.cid(charts.BTC), "bitcoin"))])
    d.cerrar()

    # 9. Fuentes y contacto ───────────────────────────────────────────────────
    d = _encabezado(prs, "Fuentes y contacto", fecha, next(numero), "Datos y contacto")
    d.panel(24, 92, 790, 592)
    d.texto(52, 116, 600, 18, "FUENTES CONSULTADAS", 11.5, CIAN, estilo.PPT_TEXTO_NEGRITA, espaciado=1)
    y = 152
    for nombre, url in presentacion.FUENTES:
        d.texto(52, y, 734, 18, nombre, 13, TINTA, estilo.PPT_TEXTO_NEGRITA)
        d.texto(52, y + 20, 734, 16, url, 10.5, CIAN, link=url)
        y += 58
    d.panel(830, 92, 426, 592)
    d.texto(858, 116, 370, 18, "CONTACTO", 11.5, CIAN, estilo.PPT_TEXTO_NEGRITA, espaciado=1)
    d.texto(858, 148, 370, 64, "Reporte hecho íntegramente en Python por Mauro E. Martinez, de GlobalAIze.", 14, TINTA)
    lado, sep = 52, 92
    for i, (icono, rotulo, url) in enumerate(presentacion.LINKS):
        izq = 850 + i * sep
        d.icono(icono, izq + (sep - lado) / 2, 236, lado, url)
        d.texto(izq, 288, sep, 30, rotulo, 9.5, SECUNDARIO, alinear=PP_ALIGN.CENTER, link=url)
    d.texto(858, 372, 370, 70, f"¿Te sirvió el reporte? Podés apoyar el proyecto al alias {presentacion.ALIAS}", 14, TINTA, estilo.PPT_TEXTO_MEDIO)
    d.texto(858, 470, 370, 70, f"Consultas, desuscripciones o propuestas:\n{presentacion.MAIL}", 13, SECUNDARIO, link=f"mailto:{presentacion.MAIL}")
    d.texto(858, 640, 370, 32, "Análisis generado con Gemini a partir de los datos del día. No es asesoramiento financiero.", 9.5, TENUE)
    d.cerrar()

    presentacion._colores_de_link(prs)
    presentacion._propiedades_de_aplicacion(prs)
    ruta = salida / ARCHIVO
    temporal = ruta.with_name(f"~tmp {ARCHIVO}")
    try:
        prs.save(temporal)
        os.replace(temporal, ruta)
    finally:
        temporal.unlink(missing_ok=True)
    return ruta

