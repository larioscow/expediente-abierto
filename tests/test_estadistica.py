"""shared/estadistica.py — verificada contra valores conocidos y propiedades."""
import math

import pytest

from shared.estadistica import (benford_first, benford_second,
                                benjamini_hochberg, fisher_exact_greater,
                                mad_benford, wilson_interval, z_digito)


class TestWilson:
    def test_valor_conocido(self):
        # 1/10 al 95%: intervalo de Wilson clásico ~ (0.018, 0.404)
        lo, hi = wilson_interval(1, 10, 0.95)
        assert lo == pytest.approx(0.0179, abs=1e-3)
        assert hi == pytest.approx(0.4046, abs=1e-3)

    def test_contiene_la_proporcion_puntual(self):
        lo, hi = wilson_interval(30, 100)
        assert lo < 0.30 < hi

    def test_extremos_se_quedan_en_rango(self):
        assert wilson_interval(0, 50)[0] == 0.0
        assert wilson_interval(50, 50)[1] == 1.0

    def test_mas_datos_estrecha(self):
        ancho = lambda k, n: (lambda lh: lh[1] - lh[0])(wilson_interval(k, n))
        assert ancho(10, 100) > ancho(100, 1000)  # misma tasa, 10× n

    def test_n_cero(self):
        assert wilson_interval(0, 0) == (0.0, 0.0)


class TestFisher:
    def test_tabla_simetrica_da_p_alto(self):
        # sin enriquecimiento: ~ la mitad de la masa en la cola
        assert fisher_exact_greater(5, 5, 5, 5) == pytest.approx(0.6718, abs=1e-3)

    def test_enriquecimiento_fuerte_da_p_bajo(self):
        # 8/10 marcadas vs 1/10 base: muy significativo
        assert fisher_exact_greater(8, 2, 1, 9) < 0.01

    def test_valor_conocido_tea_tasting(self):
        # la tabla clásica de Fisher (3,1,1,3): p de una cola = 0.2429
        assert fisher_exact_greater(3, 1, 1, 3) == pytest.approx(0.2429, abs=1e-3)

    def test_p_en_rango_y_monotonia(self):
        # más aciertos marcados (a) -> p no aumenta
        p_menos = fisher_exact_greater(4, 16, 10, 90)
        p_mas = fisher_exact_greater(12, 8, 10, 90)
        assert 0 <= p_mas <= p_menos <= 1

    def test_tabla_vacia(self):
        assert fisher_exact_greater(0, 0, 0, 0) == 1.0

    def test_rechaza_negativos(self):
        with pytest.raises(ValueError):
            fisher_exact_greater(-1, 2, 3, 4)


class TestBenford:
    def test_primer_digito_suma_uno_y_valor(self):
        b = benford_first()
        assert sum(b.values()) == pytest.approx(1.0)
        assert b[1] == pytest.approx(0.30103, abs=1e-5)

    def test_segundo_digito_suma_uno_y_es_mas_plano(self):
        b2 = benford_second()
        assert set(b2) == set(range(10))
        assert sum(b2.values()) == pytest.approx(1.0)
        assert b2[0] == pytest.approx(0.11968, abs=1e-4)
        # el segundo dígito es casi uniforme: el rango es chico vs el primero
        assert max(b2.values()) - min(b2.values()) < 0.04

    def test_z_digito_detecta_exceso(self):
        b = benford_first()
        # un dígito 1 muy sobre-representado en n grande -> Z alto
        assert z_digito(500, 1000, b[1]) > 10
        # conforme -> Z chico
        assert z_digito(301, 1000, b[1]) < 1

    def test_mad_cero_si_calza(self):
        b = benford_first()
        freq = {d: round(p * 100000) for d, p in b.items()}
        assert mad_benford(freq, sum(freq.values()), b) < 1e-4


class TestBenjaminiHochberg:
    def test_vacio(self):
        assert benjamini_hochberg([]) == []

    def test_todo_significativo_si_p_diminutos(self):
        assert benjamini_hochberg([1e-9, 1e-8, 1e-7]) == [True, True, True]

    def test_nada_si_p_altos(self):
        assert benjamini_hochberg([0.6, 0.7, 0.9]) == [False, False, False]

    def test_umbral_escalonado_conserva_orden_de_entrada(self):
        # p ordenados .001,.01,.5,.7,.8 con N=5, q=.05: umbrales .01,.02,.03,...
        # .001<=.01 ✓, .01<=.02 ✓, .5>.03 ✗ -> k_max=2; los dos menores van
        ps = [0.7, 0.001, 0.8, 0.01, 0.5]  # desordenados a propósito
        assert benjamini_hochberg(ps, q=0.05) == [False, True, False, True, False]

    def test_es_mas_potente_que_bonferroni(self):
        # con N=5 muchos p chicos: el 0.04 supera Bonferroni (.01) pero BH lo
        # rechaza (umbral .05 en el rango 5) — más potencia, FDR controlado
        ps = [0.001, 0.002, 0.003, 0.004, 0.04]
        assert benjamini_hochberg(ps, q=0.05) == [True] * 5
        assert sum(p <= 0.05 / 5 for p in ps) == 4  # Bonferroni rechaza 4
