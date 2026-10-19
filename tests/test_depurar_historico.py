import numpy as np
import pandas as pd
import pytest

import depurar_historico as dh


def _tabla(fechas, **columnas) -> pd.DataFrame:
    tabla = pd.DataFrame(index=pd.DatetimeIndex(fechas, name="Fecha"), columns=dh.NUMERICAS, dtype=float)
    for columna, valores in columnas.items():
        tabla[columna] = valores
    return tabla


def _cambios(tabla, **ref):
    referencias = {k: pd.Series(v, index=tabla.index) if not isinstance(v, pd.Series) else v for k, v in ref.items()}
    nueva, cambios = dh.correcciones(tabla, referencias)
    return nueva, cambios


def test_un_relleno_pasa_a_la_referencia_o_queda_vacio_y_conserva_su_ultimo_dia():
    fechas = pd.bdate_range("2020-01-01", periods=dh.RACHA_RELLENO + 3)
    venta = [292.0] * dh.RACHA_RELLENO + [300.0, 301.0, 302.0]
    ref_venta = pd.Series([np.nan] * 10 + list(np.linspace(80, 290, len(fechas) - 10)), index=fechas)
    tabla = _tabla(fechas, TCV_Blue=venta)
    nueva, _ = _cambios(tabla, TCV_Blue=ref_venta, TCC_Blue=ref_venta - 5)

    assert nueva["TCV_Blue"].iloc[:10].isna().all()  # sin referencia: vacío
    assert nueva["TCV_Blue"].iloc[20] == pytest.approx(ref_venta.iloc[20])
    assert nueva["TCV_Blue"].iloc[dh.RACHA_RELLENO - 1] == 292.0  # el primer dato real se conserva
    assert nueva["TCC_Blue"].iloc[20] == pytest.approx(ref_venta.iloc[20] - 5)  # la compra, de la misma fuente
    assert nueva["TCV_Blue"].iloc[-1] == 302.0


def test_una_tasa_fija_cientos_de_dias_no_es_un_relleno():
    fechas = pd.bdate_range("2023-07-27", periods=dh.RACHA_RELLENO + 30)
    tabla = _tabla(fechas, fed_tea=5.33)
    nueva, cambios = _cambios(tabla, fed_tea=pd.Series(5.33, index=fechas))
    assert cambios.empty
    assert (nueva["fed_tea"] == 5.33).all()


def test_la_coma_corrida_del_mep_se_corrige_con_la_referencia():
    fechas = pd.bdate_range("2023-01-02", periods=3)
    tabla = _tabla(fechas, TCV_MEP=[300.0, 3105.0, 312.0])
    nueva, cambios = _cambios(tabla, TCV_MEP=[301.0, 309.0, 311.0])
    assert nueva["TCV_MEP"].tolist() == [300.0, 310.5, 312.0]
    assert cambios["motivo"].tolist() == ["coma decimal corrida (x10^1)"]


@pytest.mark.parametrize("guardado, esperado", [(38.0, 3.08), (145.0, 14.05), (3125.0, 3.125)])
def test_el_billete_recupera_su_valor_exacto_contra_el_a3500(guardado, esperado):
    fecha = pd.Timestamp("2007-02-13")
    base = esperado * 0.99
    tabla = _tabla([fecha], TCC_Billete=guardado, TCV_Billete=esperado + 0.10)
    nueva, _ = _cambios(tabla, a3500=pd.Series(base, index=[fecha]))
    assert nueva.at[fecha, "TCC_Billete"] == pytest.approx(esperado)


def test_entre_dos_lecturas_queda_la_que_deja_la_compra_debajo_de_la_venta():
    fecha = pd.Timestamp("2015-07-08")
    tabla = _tabla([fecha], TCC_Billete=92.0, TCV_Billete=9.12)
    nueva, _ = _cambios(tabla, a3500=pd.Series(9.117, index=[fecha]))
    assert nueva.at[fecha, "TCC_Billete"] == pytest.approx(9.02)  # 9,20 quedaría por encima de la venta


def test_un_valor_repetido_mientras_el_mercado_se_mueve_pasa_a_la_referencia():
    fechas = pd.bdate_range("2026-08-05", periods=8)
    tabla = _tabla(fechas, TCV_Blue=[1540.0] * 8)
    ref = pd.Series([1540, 1525, 1530, 1545, 1550, 1560, 1565, 1555], index=fechas, dtype=float)
    nueva, _ = _cambios(tabla, TCV_Blue=ref)
    assert nueva["TCV_Blue"].iloc[0] == 1540.0  # el primer día sí se leyó
    assert nueva["TCV_Blue"].iloc[1:].tolist() == ref.iloc[1:].tolist()


def test_un_valor_quieto_que_coincide_con_el_mercado_no_se_toca():
    fechas = pd.bdate_range("2023-08-15", periods=8)
    tabla = _tabla(fechas, TCV_Blue=[730.0] * 8)
    _, cambios = _cambios(tabla, TCV_Blue=pd.Series(730.0, index=fechas))
    assert cambios.empty


def test_la_fed_mal_cargada_pasa_a_la_effr_de_ese_dia():
    fechas = pd.bdate_range("2023-05-10", periods=3)
    tabla = _tabla(fechas, fed_tea=[58.0, 5.08, 5.08])
    effr = pd.Series([5.08], index=[pd.Timestamp("2023-05-09")])  # publicada con un día de rezago
    nueva, _ = _cambios(tabla, fed_tea=effr)
    assert nueva["fed_tea"].tolist() == [5.08, 5.08, 5.08]


def test_compra_mayor_que_venta_deja_vacio_el_que_se_aparta_de_su_semana():
    fechas = pd.bdate_range("2024-01-22", periods=7)
    tabla = _tabla(fechas, TCC_Euro=[1270, 1268, 1272, 1902, 1275, 1271, 1269],
                   TCV_Euro=[1330, 1328, 1331, 1332, 1334, 1330, 1329])
    nueva, cambios = _cambios(tabla)
    assert np.isnan(nueva.at[fechas[3], "TCC_Euro"])
    assert nueva.at[fechas[3], "TCV_Euro"] == 1332
    assert cambios["motivo"].tolist() == ["compra mayor que venta"]


def test_sin_errores_no_hay_cambios():
    fechas = pd.bdate_range("2026-10-01", periods=5)
    tabla = _tabla(fechas, TCV_Blue=[1500.0, 1505.0, 1510.0, 1508.0, 1512.0], TCV_MEP=[1490.0, 1495, 1500, 1498, 1501])
    _, cambios = _cambios(tabla, TCV_Blue=tabla["TCV_Blue"], TCV_MEP=tabla["TCV_MEP"])
    assert cambios.empty
