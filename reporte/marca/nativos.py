"""Gráficos nativos de PowerPoint con la estética de GlobalAIze (para la presentación de prueba).

Mismos datos y misma lógica que reporte/graficos_pptx.py, que no cambia: lo que se
reemplaza es el estilo. Fondo transparente (se ve el vidrio de la diapositiva),
letra clara, grilla apenas visible y la paleta de series de la marca. Lo que no es
de estilo (la escala de los ejes, el eje secundario de la inflación, el eje de
fechas) se importa de graficos_pptx.
"""

from datetime import date

from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE
from pptx.enum.dml import MSO_LINE
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls, qn
from pptx.util import Pt

from reporte import charts, transformations
from reporte.graficos_pptx import (
    EJE_Y2,
    _a_linea_en_eje_secundario,
    _es,
    _escala,
    _escala_secundaria,
    _etiqueta_final,
    _meses_en_el_eje,
    _ultimas_ruedas,
    _valores,
)
from reporte.marca import estilo
from reporte.marca.graficos import OFICIALES, PARALELAS


def _rgb(hexa: str) -> RGBColor:
    return RGBColor.from_string(hexa.lstrip("#").upper())


TINTA, SECUNDARIO = _rgb(estilo.TINTA), _rgb(estilo.SECUNDARIO)
GRILLA = _rgb("1B3A68")  # el 8 % de blanco sobre el vidrio, ya mezclado (los gráficos nativos no aceptan alfa en la línea)
CIAN, VIOLETA, OLIVA = _rgb(estilo.CIAN), _rgb(estilo.VIOLETA), _rgb(estilo.OLIVA)
MALO, BUENO = _rgb(estilo.MALO), _rgb(estilo.BUENO)
SIN_RELLENO = '<c:spPr {ns}><a:noFill/><a:ln><a:noFill/></a:ln></c:spPr>'


def _transparente(grafico) -> None:
    """Sin fondo ni borde en el gráfico y en el área de trazado, para que se vea el vidrio de atrás."""
    espacio = grafico._chartSpace
    for padre, despues in ((espacio, espacio.find(qn("c:chart"))), ):
        previo = padre.find(qn("c:spPr"))
        if previo is not None:
            padre.remove(previo)
        despues.addnext(parse_xml(SIN_RELLENO.format(ns=nsdecls("c", "a"))))
    area = espacio.chart.plotArea
    previo = area.find(qn("c:spPr"))
    if previo is not None:
        area.remove(previo)
    area.append(parse_xml(SIN_RELLENO.format(ns=nsdecls("c", "a"))))


def _base(grafico, leyenda: bool = True) -> None:
    grafico.font.name = estilo.PPT_TEXTO
    grafico.font.size = Pt(10)
    grafico.font.color.rgb = SECUNDARIO
    grafico.has_title = False
    grafico.has_legend = leyenda
    if leyenda:
        grafico.legend.position = XL_LEGEND_POSITION.TOP
        grafico.legend.include_in_layout = False
        grafico.legend.font.size = Pt(10)
        grafico.legend.font.color.rgb = SECUNDARIO
    eje = grafico.value_axis
    eje.has_major_gridlines = True
    eje.major_gridlines.format.line.color.rgb = GRILLA
    eje.major_gridlines.format.line.width = Pt(0.75)
    eje.format.line.fill.background()
    eje.tick_labels.font.color.rgb = SECUNDARIO
    grafico.category_axis.format.line.color.rgb = GRILLA
    grafico.category_axis.tick_labels.font.color.rgb = SECUNDARIO
    _transparente(grafico)


def _rotulos_horizontales(grafico, salto: int = 1) -> None:
    """Rótulos del eje de categorías en horizontal y, con `salto` > 1, uno de cada `salto`: sin esto PowerPoint los gira o los tapa."""
    eje = grafico.category_axis
    eje.tick_labels.font.size = Pt(9.5)  # crea el txPr del eje
    cuerpo = eje._element.find(qn("c:txPr")).find(qn("a:bodyPr"))
    cuerpo.set("rot", "0")
    cuerpo.set("vert", "horz")
    if salto > 1:
        cierre = eje._element.find(qn("c:noMultiLvlLbl"))
        saltos = [parse_xml(f'<c:tickLblSkip {nsdecls("c")} val="{salto}"/>'), parse_xml(f'<c:tickMarkSkip {nsdecls("c")} val="{salto}"/>')]
        for nodo in saltos:
            if cierre is not None:
                cierre.addprevious(nodo)
            else:
                eje._element.append(nodo)


def _eje_valores(grafico, valores, formato: str, desde_cero: bool = False) -> None:
    bajo, alto, paso = _escala(valores)
    eje = grafico.value_axis
    eje.minimum_scale, eje.maximum_scale, eje.major_unit = (0 if desde_cero else bajo), alto, paso
    eje.tick_labels.number_format = formato
    eje.tick_labels.number_format_is_linked = False


def _lineas(slide, x, y, ancho, alto, categorias, series, formato: str, marcadores: bool = True):
    """`series` es [(nombre, valores, color, discontinua)]."""
    datos = CategoryChartData(number_format=formato)
    datos.categories = categorias
    for nombre, valores, *_ in series:
        datos.add_series(nombre, valores)
    tipo = XL_CHART_TYPE.LINE_MARKERS if marcadores else XL_CHART_TYPE.LINE
    grafico = slide.shapes.add_chart(tipo, x, y, ancho, alto, datos).chart
    _base(grafico)
    for serie, (_, _, color, discontinua) in zip(grafico.plots[0].series, series):
        serie.smooth = False
        serie.format.line.color.rgb = color
        serie.format.line.width = Pt(2.25)
        if discontinua:
            serie.format.line.dash_style = MSO_LINE.DASH
        if marcadores:
            serie.marker.style = XL_MARKER_STYLE.NONE if discontinua else XL_MARKER_STYLE.CIRCLE
            if not discontinua:
                serie.marker.size = 4
                serie.marker.format.fill.solid()
                serie.marker.format.fill.fore_color.rgb = color
                serie.marker.format.line.color.rgb = color
    _eje_valores(grafico, [v for _, valores, *_ in series for v in valores], formato)
    if not isinstance(categorias[0], date):
        _rotulos_horizontales(grafico, 3)
    return grafico


def _con_columnas(slide, x, y, ancho, alto, df, columnas, formato: str = "#,##0"):
    ultimos = _ultimas_ruedas(df)
    series = [(rotulo, _valores(ultimos[col]), _rgb(color), trazo == "--") for col, rotulo, color, trazo in columnas]
    return _lineas(slide, x, y, ancho, alto, [f[:5] for f in ultimos["Fecha"]], series, formato)


def paralelas(slide, x, y, ancho, alto, df):
    return _con_columnas(slide, x, y, ancho, alto, df, PARALELAS)


def oficiales(slide, x, y, ancho, alto, df):
    return _con_columnas(slide, x, y, ancho, alto, df, OFICIALES)


def riesgo_pais(slide, x, y, ancho, alto, df):
    """Barras en cian, el máximo de la ventana en rojo y el mínimo en verde, con el valor arriba de cada una."""
    ultimos = _ultimas_ruedas(df)
    valores = _valores(ultimos["riesgo_pais"])
    datos = CategoryChartData(number_format="#,##0")
    datos.categories = [f[:5] for f in ultimos["Fecha"]]
    datos.add_series("Riesgo país (puntos básicos)", valores)
    grafico = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, x, y, ancho, alto, datos).chart
    _base(grafico, leyenda=False)
    barras = grafico.plots[0]
    barras.gap_width = 35
    serie = barras.series[0]
    serie.format.fill.solid()
    serie.format.fill.fore_color.rgb = CIAN
    presentes = [v for v in valores if v is not None]
    maximo, minimo = max(presentes), min(presentes)
    for i, valor in enumerate(valores):
        if valor in (maximo, minimo):
            punto = serie.points[i].format.fill
            punto.solid()
            punto.fore_color.rgb = MALO if valor == maximo else BUENO
    barras.has_data_labels = True
    etiquetas = barras.data_labels
    etiquetas.number_format, etiquetas.number_format_is_linked = "#,##0", False
    etiquetas.position = XL_LABEL_POSITION.OUTSIDE_END
    etiquetas.font.size = Pt(9)
    etiquetas.font.color.rgb = TINTA
    _eje_valores(grafico, [0, maximo * 1.12], "#,##0", desde_cero=True)
    _rotulos_horizontales(grafico, 2)
    return grafico


def _estilo_eje_secundario(grafico, color: RGBColor) -> None:
    """Letra de color en el eje derecho y sin línea: el que arma graficos_pptx trae el estilo por defecto."""
    eje = next(e for e in grafico._chartSpace.chart.plotArea.findall(qn("c:valAx")) if e.find(qn("c:axId")).get("val") == EJE_Y2)
    rotulos = eje.find(qn("c:tickLblPos"))
    texto = parse_xml(
        f'<c:txPr {nsdecls("c", "a")}><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="1000">'
        f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="{estilo.PPT_TEXTO}"/></a:defRPr></a:pPr>'
        '<a:endParaRPr lang="es-AR"/></a:p></c:txPr>'
    )
    rotulos.addnext(texto)
    rotulos.addnext(parse_xml(f'<c:spPr {nsdecls("c", "a")}><a:ln><a:noFill/></a:ln></c:spPr>'))


def rango_anual(anual) -> float:
    """Cuánto se mueve la interanual en la ventana: la escala deja abajo ese aire para que las barras no se pisen con la línea."""
    presentes = [v for v in anual if v is not None]
    return (max(presentes) - min(presentes)) or 1.0


def inflacion(slide, x, y, ancho, alto, serie):
    """Inflación mensual en barras (cian) e interanual en línea (violeta) sobre un eje derecho, de los últimos 12 meses."""
    ultimos = transformations.ultimos_meses(serie)
    mensual, anual = _valores(ultimos["Inflación Mensual"]), _valores(ultimos["Inflación Anual"])
    datos = CategoryChartData(number_format='0.0"%"')
    datos.categories = [transformations.etiqueta_mes(f) for f in ultimos["Fecha"]]
    datos.add_series("Inflación mensual", mensual)
    datos.add_series("Inflación interanual (eje derecho)", anual)
    grafico = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, x, y, ancho, alto, datos).chart
    _base(grafico)
    _eje_valores(grafico, [0, max(v for v in mensual if v is not None) * 1.9], '0.0"%"', desde_cero=True)
    barras = grafico.plots[0]
    barras.gap_width = 55
    columnas = barras.series[0]
    columnas.format.fill.solid()
    columnas.format.fill.fore_color.rgb = CIAN
    barras.has_data_labels = True
    etiquetas = barras.data_labels
    etiquetas.number_format, etiquetas.number_format_is_linked = '0.0"%"', False
    etiquetas.position = XL_LABEL_POSITION.OUTSIDE_END
    etiquetas.font.size = Pt(9)
    etiquetas.font.color.rgb = TINTA
    _a_linea_en_eje_secundario(grafico)

    linea = grafico.plots[1].series[0]
    linea.smooth = False
    linea.format.line.color.rgb = VIOLETA
    linea.format.line.width = Pt(2.75)
    linea.marker.style = XL_MARKER_STYLE.CIRCLE
    linea.marker.size = 7
    linea.marker.format.fill.solid()
    linea.marker.format.fill.fore_color.rgb = VIOLETA
    linea.marker.format.line.color.rgb = VIOLETA
    if any(v is not None for v in anual):
        _escala_secundaria(grafico, anual + [min(v for v in anual if v is not None) - 2.2 * rango_anual(anual),
                                            max(v for v in anual if v is not None) + 0.6 * rango_anual(anual)])
        _etiqueta_final(linea, anual, f"{_es(next(v for v in reversed(anual) if v is not None))}%", TINTA)
    _estilo_eje_secundario(grafico, estilo.VIOLETA.lstrip("#"))
    return grafico


def variaciones(slide, x, y, ancho, alto, df, serie):
    """Solidario, blue e inflación acumulados desde charts.FECHA_INICIO_VARIACIONES, en un eje de fechas."""
    data = charts.preparar_datos(transformations.agregar_brechas_y_variaciones(df))
    va = charts.preparar_variaciones(data, serie).dropna(subset=["Fecha"])
    columnas = [("Solidario", "Variación Solidario Acumulada", _rgb(estilo.VERDE_AZULADO)),
                ("Blue", "Variación TCV Blue Acumulada", CIAN), ("Inflación", "Inflación Mensual Acumulada", OLIVA)]
    # La inflación es mensual y las cotizaciones diarias: se completa hacia adelante, como el escalón del mail
    va[[c for _, c, _ in columnas]] = va[[c for _, c, _ in columnas]].ffill()
    series = [(f"{nombre} acumulado", _valores(va[col]), color, False) for nombre, col, color in columnas]
    if not all(any(v is not None for v in valores) for _, valores, *_ in series):
        raise ValueError("faltan datos para alguna de las variaciones acumuladas")
    grafico = _lineas(slide, x, y, ancho, alto, [f.date() for f in va["Fecha"]], series, '0"%"', marcadores=False)
    grafico.category_axis.tick_labels.number_format = "mmm-yy"
    grafico.category_axis.tick_labels.number_format_is_linked = False
    meses = max(1, (va["Fecha"].iloc[-1] - va["Fecha"].iloc[0]).days // 30)
    _meses_en_el_eje(grafico, 1 if meses <= 8 else 2 if meses <= 16 else 3)
    return grafico


