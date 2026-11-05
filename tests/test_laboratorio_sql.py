import json
from pathlib import Path

import pandas as pd
import pytest

from scripts import depurar_historico as depuracion


@pytest.mark.parametrize("factor", [1, 10, 100, 1000, 0.1])
def test_auditoria_del_notebook_detecta_escala_sin_escribir(monkeypatch, factor):
    notebook = json.loads((Path(__file__).resolve().parents[1] / "notebooks/laboratorio_sql.ipynb").read_text(encoding="utf-8"))
    tabla = pd.DataFrame({col: [float("nan")] for col in depuracion.NUMERICAS})
    tabla["Fecha"] = ["2026-10-06"]
    tabla["TCV_MEP"] = [1500 * factor]
    original = tabla.copy(deep=True)
    referencia = pd.Series([1500.0], index=pd.to_datetime(tabla["Fecha"], format="%Y-%m-%d"))
    monkeypatch.setattr(depuracion, "bajar_referencias", lambda desde: {"TCV_MEP": referencia})

    def prohibido(*args, **kwargs):
        pytest.fail("La auditoría no debe aplicar cambios ni usar el CLI")

    monkeypatch.setattr(depuracion, "aplicar", prohibido)
    monkeypatch.setattr(depuracion, "main", prohibido)

    def consulta(sql):
        assert sql == 'SELECT * FROM "Fact_Mercado_Macro" ORDER BY "Fecha"'
        return tabla.copy(deep=True)

    entorno = {"pd": pd, "consulta": consulta, "display": lambda objeto: None}
    for celda in notebook["cells"]:
        if celda["cell_type"] == "code" and celda["id"].startswith("auditoria-"):
            exec(compile("".join(celda["source"]), celda["id"], "exec"), entorno)
    hallazgos = entorno["errores_escala"]
    if factor == 1:
        assert hallazgos.empty
    else:
        assert hallazgos.iloc[0]["despues"] == pytest.approx(1500)
        assert hallazgos.iloc[0]["factor_antes_sobre_despues"] == pytest.approx(factor)
    pd.testing.assert_frame_equal(tabla, original)
