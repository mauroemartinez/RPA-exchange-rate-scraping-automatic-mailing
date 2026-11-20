"""Transiciones y animaciones de entrada para la presentación, con XML de PowerPoint (python-pptx no las expone).

* transicion(): un fundido suave al pasar de una diapositiva a la otra.
* entradas(): al abrirse la diapositiva, los gráficos y las imágenes entran con un barrido de izquierda a derecha y
  los textos con un fundido, escalonados para que se lea en el orden en que se cuenta. Arrancan solos ("después de
  la anterior"): no hace falta hacer clic, y en una presentación enviada por mail o vista en la PC se ve igual.

El XML sigue lo que escribe PowerPoint para "Aparecer / Fundido" (presetID 10) y "Barrido" (presetID 22), con la
estructura de la secuencia principal. Todo animable es una forma ya existente de la diapositiva: no se agrega ninguna.
"""

from pptx.oxml import parse_xml

NS = 'xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"'
DURACION_MS = 600
ESCALON_MS = 220  # cuánto después de la anterior entra cada una


def transicion(slide, tipo: str = "fade") -> None:
    """Fundido al entrar en la diapositiva. Va después de clrMapOvr y antes de timing, como pide el esquema."""
    elemento = slide._element
    for previo in elemento.findall("{http://schemas.openxmlformats.org/presentationml/2006/main}transition"):
        elemento.remove(previo)
    nodo = parse_xml(f'<p:transition {NS} spd="med"><p:{tipo}/></p:transition>')
    mapa = elemento.find("{http://schemas.openxmlformats.org/presentationml/2006/main}clrMapOvr")
    if mapa is not None:
        mapa.addnext(nodo)
    else:
        elemento.find("{http://schemas.openxmlformats.org/presentationml/2006/main}cSld").addnext(nodo)


def _efecto(ids, shape_id: int, efecto: str, retraso: int, primero: bool) -> str:
    """Una entrada de la secuencia: el <p:par> de un efecto sobre una forma."""
    id_externo, id_set, id_anim = next(ids), next(ids), next(ids)
    if efecto == "wipe":
        preset, subtipo, filtro = 22, 8, "wipe(left)"  # barrido desde la izquierda
    else:
        preset, subtipo, filtro = 10, 0, "fade"
    nodo = "afterEffect" if primero else "withEffect"
    return (
        f'<p:par><p:cTn id="{id_externo}" presetID="{preset}" presetClass="entr" presetSubtype="{subtipo}" fill="hold" '
        f'nodeType="{nodo}"><p:stCondLst><p:cond delay="{retraso}"/></p:stCondLst><p:childTnLst>'
        f'<p:set><p:cBhvr><p:cTn id="{id_set}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
        f'<p:tgtEl><p:spTgt spid="{shape_id}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName>'
        f'</p:attrNameLst></p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>'
        f'<p:animEffect transition="in" filter="{filtro}"><p:cBhvr><p:cTn id="{id_anim}" dur="{DURACION_MS}"/>'
        f'<p:tgtEl><p:spTgt spid="{shape_id}"/></p:tgtEl></p:cBhvr></p:animEffect>'
        f'</p:childTnLst></p:cTn></p:par>'
    )


def entradas(slide, items: list[tuple]) -> int:
    """Anima la entrada de `items` = [(forma, "fade" | "wipe")], en ese orden, solas al abrir la diapositiva.

    Devuelve cuántas animó. Sin items no escribe nada.
    """
    if not items:
        return 0
    ids = iter(range(5, 10_000))
    efectos = "".join(
        _efecto(ids, forma.shape_id, efecto, i * ESCALON_MS, i == 0) for i, (forma, efecto) in enumerate(items)
    )
    timing = parse_xml(
        f'<p:timing {NS}><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
        '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
        '<p:par><p:cTn id="3" fill="hold"><p:stCondLst><p:cond delay="indefinite"/>'
        '<p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst><p:childTnLst>'
        '<p:par><p:cTn id="4" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst><p:childTnLst>'
        f'{efectos}'
        '</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>'
        '</p:childTnLst></p:cTn><p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>'
        '</p:prevCondLst><p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond>'
        '</p:nextCondLst></p:seq></p:childTnLst></p:cTn></p:par></p:tnLst></p:timing>'
    )
    elemento = slide._element
    for previo in elemento.findall("{http://schemas.openxmlformats.org/presentationml/2006/main}timing"):
        elemento.remove(previo)
    # Orden del esquema: cSld, clrMapOvr, transition, timing, extLst
    anterior = elemento.find("{http://schemas.openxmlformats.org/presentationml/2006/main}transition")
    if anterior is None:
        anterior = elemento.find("{http://schemas.openxmlformats.org/presentationml/2006/main}clrMapOvr")
    anterior.addnext(timing)
    return len(items)
