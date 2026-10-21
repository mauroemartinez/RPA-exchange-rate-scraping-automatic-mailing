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
    assert cambios["motivo"].tolist() == ["compra mayor que venta, sin referencia: queda vacío"]


def test_compra_mayor_que_venta_con_referencia_toma_el_dato_real():
    fechas = pd.bdate_range("2024-01-22", periods=7)
    tabla = _tabla(fechas, TCC_Euro=[1270, 1268, 1272, 1902, 1275, 1271, 1269],
                   TCV_Euro=[1330, 1328, 1331, 1332, 1334, 1330, 1329])
    nueva, _ = _cambios(tabla, TCC_Euro=pd.Series([1301.5], index=[fechas[3]]),
                        TCV_Euro=pd.Series([1332.0], index=[fechas[3]]))
    assert nueva.at[fechas[3], "TCC_Euro"] == 1301.5
    assert nueva.at[fechas[3], "TCV_Euro"] == 1332


@pytest.mark.parametrize("guardado, banco, motivo", [
    (38.0, 3.08, "cero perdido"), (185.0, 18.05, "cero perdido"), (3155.0, 3.155, "x10^3"), (17785.0, 17.785, "x10^3"),
])
def test_el_billete_vuelve_al_valor_exacto_del_banco_nacion(guardado, banco, motivo):
    fecha = pd.Timestamp("2007-10-24")
    tabla = _tabla([fecha], TCC_Billete=guardado)
    nueva, cambios = _cambios(tabla, TCC_Billete=pd.Series(banco, index=[fecha]))
    assert nueva.at[fecha, "TCC_Billete"] == banco
    assert motivo in cambios["motivo"].iloc[0] and "Banco Nación" in cambios["motivo"].iloc[0]


def test_una_diferencia_chica_con_el_banco_no_se_toca():
    # El scraper lee a las 16; el histórico del banco tiene el cierre: no es un error
    fecha = pd.Timestamp("2026-03-30")
    tabla = _tabla([fecha], TCC_Billete=1355.0, TCV_Billete=1405.0)
    _, cambios = _cambios(tabla, TCC_Billete=pd.Series(1370.0, index=[fecha]),
                          TCV_Billete=pd.Series(1420.0, index=[fecha]))
    assert cambios.empty


def test_la_fila_con_dia_y_mes_invertidos_vuelve_a_su_dato():
    # El 11/01/2022 tenía el billete y el MEP del 01/11/2022; su vecino es el 10/01
    fechas = pd.DatetimeIndex(["2022-01-10", "2022-01-11", "2022-11-01"])
    tabla = _tabla(fechas, TCC_Billete=[102.5, 155.0, 155.0], TCV_Billete=[108.5, 163.0, 163.0],
                   TCV_MEP=[200.0, 290.41, 290.41], riesgo_pais=[1821.0, 1820.0, 2568.0], fed_tea=[0.08, 3.08, 3.08])
    nueva, cambios = _cambios(tabla, TCC_Billete=[102.5, 102.5, 155.0], TCV_Billete=[108.5, 108.5, 163.0],
                              TCV_MEP=[201.0, 202.0, 290.0])
    assert nueva.loc["2022-01-11", ["TCC_Billete", "TCV_Billete", "TCV_MEP"]].tolist() == [102.5, 108.5, 202.0]
    assert nueva.at[pd.Timestamp("2022-01-11"), "riesgo_pais"] == 1820.0  # distinto del 01/11: no se copió
    assert nueva.loc["2022-11-01"].equals(tabla.loc["2022-11-01"])  # la fecha buena no se toca
    assert set(cambios["motivo"]) == {"día y mes invertidos: es el dato del 01/11/2022"}


def test_dos_fechas_invertidas_con_el_mismo_billete_real_no_son_una_copia():
    # En 2023 el oficial estuvo fijo: el 11/09 y el 09/11 tienen el mismo billete de verdad
    fechas = pd.DatetimeIndex(["2023-09-11", "2023-11-09"])
    tabla = _tabla(fechas, TCC_Billete=[350.0, 350.0], TCV_Billete=[365.5, 365.5])
    _, cambios = _cambios(tabla, TCC_Billete=[350.0, 350.0], TCV_Billete=[365.5, 365.5])
    assert cambios.empty


def test_el_blue_de_referencia_es_la_venta_de_dolarhoy_con_la_compra_de_su_misma_fuente():
    fechas = pd.DatetimeIndex(["2010-12-30", "2026-08-10", "2026-09-01", "2026-09-02"])
    dolarhoy = pd.Series([1535.0, 1545.0, 1540.0], index=fechas[1:])
    ambito = pd.DataFrame({"compra": [3.95, 1505.0, 1535.0, 1520.0], "venta": [3.98, 1525.0, 1555.0, 1540.0]}, index=fechas)
    argentinadatos = pd.DataFrame({"compra": [1515.0, 1535.0, 1525.0], "venta": [1535.0, 1555.0, 1545.0]}, index=fechas[1:])
    compra, venta = dh.referencias_blue(dolarhoy, ambito, argentinadatos)
    assert venta.tolist() == [3.98, 1535.0, 1545.0, 1540.0]  # antes de 2011, Ámbito
    assert compra.iloc[0] == 3.95 and compra.iloc[1] == 1515.0  # ArgentinaDatos coincide con DolarHoy
    assert np.isnan(compra.iloc[2])  # ninguna coincide: sin compra antes que mezclar fuentes
    assert compra.iloc[3] == 1520.0  # Ámbito coincide


def test_el_blue_trabado_toma_compra_y_venta_de_la_referencia():
    fechas = pd.bdate_range("2026-08-05", periods=6)
    tabla = _tabla(fechas, TCC_Blue=[1520.0] * 6, TCV_Blue=[1540.0] * 6)
    venta = pd.Series([1540, 1525, 1535, 1550, 1540, 1545], index=fechas, dtype=float)
    compra = pd.Series([1520, 1505, np.nan, 1530, 1520, 1525], index=fechas, dtype=float)
    nueva, _ = _cambios(tabla, TCV_Blue=venta, TCC_Blue=compra)
    assert nueva["TCV_Blue"].tolist() == venta.tolist()
    assert nueva["TCC_Blue"].iloc[[0, 1, 3]].tolist() == [1520.0, 1505.0, 1530.0]
    assert np.isnan(nueva["TCC_Blue"].iloc[2])  # sin compra de referencia ese día, vacío y no trabado


def test_el_euro_que_la_fuente_dejo_de_publicar_queda_vacio():
    fechas = pd.bdate_range("2026-05-05", periods=dh.RACHA_EURO + 2)
    tabla = _tabla(fechas, TCC_Euro=1630.2, TCV_Euro=1653.57)
    nueva, _ = _cambios(tabla, TCV_Euro=pd.Series([1653.57], index=fechas[:1]))
    assert nueva["TCV_Euro"].iloc[0] == 1653.57
    assert nueva["TCV_Euro"].iloc[1:].isna().all()


def test_sin_errores_no_hay_cambios():
    fechas = pd.bdate_range("2026-10-01", periods=5)
    tabla = _tabla(fechas, TCV_Blue=[1500.0, 1505.0, 1510.0, 1508.0, 1512.0], TCV_MEP=[1490.0, 1495, 1500, 1498, 1501])
    _, cambios = _cambios(tabla, TCV_Blue=tabla["TCV_Blue"], TCV_MEP=tabla["TCV_MEP"])
    assert cambios.empty


def test_la_compra_faltante_sale_de_la_misma_fuente_que_la_venta():
    fechas = pd.bdate_range("2005-03-07", periods=3)
    tabla = _tabla(fechas, TCV_Blue=[2.93, 2.93, 2.94])
    # El 08/03/2005 Ámbito tiene compra igual a venta: es un dato real
    nueva, _ = _cambios(tabla, TCC_Blue=[2.92, 2.93, 2.93], TCV_Blue=[2.93, 2.93, 2.95])
    assert nueva["TCC_Blue"].iloc[:2].tolist() == [2.92, 2.93]
    assert np.isnan(nueva["TCC_Blue"].iloc[2])  # la venta no es la de esa fuente: no se mezcla
