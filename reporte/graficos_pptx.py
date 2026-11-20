"""Ayudantes de los gráficos nativos de PowerPoint de la presentación.

Los gráficos en sí (paralelas, oficiales, riesgo país, inflación y variaciones) están en
reporte/marca/nativos.py, con el estilo de GlobalAIze. Acá quedan los ayudantes que no son de
estilo: la escala redonda de los ejes, las etiquetas finales, el eje secundario de la inflación
(python-pptx no arma gráficos combinados, así que se mueve la segunda serie a un lineChart) y el
eje de fechas.

Los ejes llevan formatos numéricos ("#,##0", '0.0"%"', "mmm-yy") y no texto, así que PowerPoint los
muestra con la configuración regional de quien abre el archivo: en una PC en español de Argentina,
1.500 y sep-26; en una en inglés, 1,500 y Sep-26. Es lo esperable. Solo las etiquetas escritas como
texto (el último valor de la inflación interanual) salen siempre en formato argentino.
"""

import math

import pandas as pd
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_LABEL_POSITION
from pptx.oxml import parse_xml
from pptx.oxml.ns import nsdecls, qn
from pptx.util import Pt

from reporte import charts

# Ids de los ejes secundarios del gráfico de inflación: cualquier número que no usen los primarios
EJE_X2, EJE_Y2 = "50020001", "50020002"


def _valores(serie) -> list[float | None]:
    """Los vacíos van como None: PowerPoint no acepta 'nan' en los datos del gráfico y pide repararlo."""
    return [None if pd.isna(v) else float(v) for v in serie]


def _es(valor: float, decimales: int = 1) -> str:
    """Formato argentino para las etiquetas escritas a mano: 1234.5 da '1.234,5'."""
    return f"{valor:,.{decimales}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _escala(valores, divisiones: int = 5) -> tuple[float, float, float]:
    """(mínimo, máximo, paso) redondos para el eje.

    PowerPoint arranca el eje en cero cuando el mínimo no está cerca del máximo, y
    cotizaciones de 1.500 a 2.000 quedarían como líneas planas arriba de todo.
    """
    limpios = [v for v in valores if v is not None]
    bajo, alto = min(limpios), max(limpios)
    if alto == bajo:
        bajo, alto = bajo - 1, alto + 1
    crudo = (alto - bajo) / divisiones
    potencia = 10 ** math.floor(math.log10(crudo))
    paso = next(m * potencia for m in (1, 2, 2.5, 5, 10) if m * potencia >= crudo)
    return math.floor(bajo / paso) * paso, math.ceil(alto / paso) * paso, paso


def _etiqueta_final(serie, valores, texto: str, color: RGBColor) -> None:
    """El valor del último punto, arriba de él: a la derecha chocaría con el eje derecho."""
    ultimo = max(i for i, v in enumerate(valores) if v is not None)
    etiqueta = serie.points[ultimo].data_label
    etiqueta.has_text_frame = True
    etiqueta.text_frame.text = texto
    etiqueta.position = XL_LABEL_POSITION.ABOVE
    fuente = etiqueta.text_frame.paragraphs[0].font
    fuente.size, fuente.bold, fuente.color.rgb = Pt(9), True, color


def _ultimas_ruedas(df, n: int = charts.COTIZACIONES_A_MOSTRAR) -> pd.DataFrame:
    """Las últimas n ruedas, de la más vieja a la más nueva, con la fecha como 'dd/mm/yy' (como el mail)."""
    return charts.preparar_datos(df).tail(n)


def _a_linea_en_eje_secundario(grafico) -> None:
    """Pasa la segunda serie de las barras a una línea con su propio eje, a la derecha.

    python-pptx no arma gráficos combinados: se crean las dos series como barras (así
    la planilla incrustada las tiene a las dos) y la segunda se mueve a un lineChart
    con un par de ejes nuevos, que es como guarda PowerPoint un gráfico combinado.
    """
    area = grafico._chartSpace.chart.plotArea
    barras = area.find(qn("c:barChart"))
    serie = barras.findall(qn("c:ser"))[1]
    barras.remove(serie)
    invertir = serie.find(qn("c:invertIfNegative"))
    if invertir is not None:
        serie.remove(invertir)  # no existe en las series de línea: PowerPoint pediría reparar el archivo
    linea = parse_xml(
        f'<c:lineChart {nsdecls("c")}><c:grouping val="standard"/><c:varyColors val="0"/>'
        f'<c:marker val="1"/><c:axId val="{EJE_X2}"/><c:axId val="{EJE_Y2}"/></c:lineChart>'
    )
    linea.insert(2, serie)
    barras.addnext(linea)
    ejes = parse_xml(
        f'<c:plotArea {nsdecls("c")}>'
        f'<c:catAx><c:axId val="{EJE_X2}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
        '<c:delete val="1"/><c:axPos val="b"/><c:majorTickMark val="none"/><c:minorTickMark val="none"/>'
        f'<c:tickLblPos val="nextTo"/><c:crossAx val="{EJE_Y2}"/><c:crosses val="autoZero"/>'
        '<c:auto val="1"/><c:lblAlgn val="ctr"/><c:lblOffset val="100"/><c:noMultiLvlLbl val="0"/></c:catAx>'
        f'<c:valAx><c:axId val="{EJE_Y2}"/><c:scaling><c:orientation val="minMax"/></c:scaling>'
        '<c:delete val="0"/><c:axPos val="r"/><c:numFmt formatCode="0.0&quot;%&quot;" sourceLinked="0"/>'
        '<c:majorTickMark val="out"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/>'
        f'<c:crossAx val="{EJE_X2}"/><c:crosses val="max"/><c:crossBetween val="between"/></c:valAx>'
        "</c:plotArea>"
    )
    ultimo_eje = area.findall(qn("c:valAx"))[-1]
    for eje in reversed(list(ejes)):
        ultimo_eje.addnext(eje)


def _escala_secundaria(grafico, valores) -> None:
    """Mínimo y máximo del eje derecho, para que la interanual no quede aplastada contra cero."""
    bajo, alto, _ = _escala(valores)
    eje = next(e for e in grafico._chartSpace.chart.plotArea.findall(qn("c:valAx"))
               if e.find(qn("c:axId")).get("val") == EJE_Y2)
    escala = eje.find(qn("c:scaling"))
    escala.append(parse_xml(f'<c:max {nsdecls("c")} val="{alto}"/>'))
    escala.append(parse_xml(f'<c:min {nsdecls("c")} val="{bajo}"/>'))


def _meses_en_el_eje(grafico, cada: int) -> None:
    """Un rótulo cada `cada` meses en el eje de fechas: python-pptx no lo expone."""
    eje = grafico._chartSpace.chart.plotArea.find(qn("c:dateAx"))
    for etiqueta in ("c:baseTimeUnit", "c:majorUnit", "c:majorTimeUnit"):
        viejo = eje.find(qn(etiqueta))
        if viejo is not None:
            eje.remove(viejo)
    nuevos = [parse_xml(f'<c:baseTimeUnit {nsdecls("c")} val="days"/>'),
              parse_xml(f'<c:majorUnit {nsdecls("c")} val="{cada}"/>'),
              parse_xml(f'<c:majorTimeUnit {nsdecls("c")} val="months"/>')]
    # Van antes de minorUnit, minorTimeUnit o extLst, si los hay; si no, al final
    siguiente = next((eje.find(qn(e)) for e in ("c:minorUnit", "c:minorTimeUnit", "c:extLst")
                      if eje.find(qn(e)) is not None), None)
    for nuevo in nuevos:
        if siguiente is None:
            eje.append(nuevo)
        else:
            siguiente.addprevious(nuevo)
