"""Pruebas de los módulos extraídos del motor en la refactorización: filtros, presentación y exportación."""
import json
import os
import tempfile
import unittest
from decimal import Decimal as D

from helpers import REGLAS, ruta_datos
from nucleo import exportacion, filtros, presentacion as pres
from nucleo.procesador import procesar_archivo


class TestAnalizadoresDeFiltros(unittest.TestCase):
    def test_valores_validos(self):
        self.assertEqual(filtros.parsear_estado(REGLAS, " success "), "SUCCESS")
        self.assertEqual(filtros.parsear_moneda(REGLAS, "eur"), "EUR")
        self.assertEqual(filtros.parsear_fuente(REGLAS, "FUENTE_b"), "fuente_B")
        self.assertEqual(filtros.parsear_monto("99,50"), D("99.50"))
        self.assertEqual(filtros.parsear_fecha("2025-03-10"), "2025-03-10")

    def test_vacio_quita_el_filtro(self):
        for f in (lambda t: filtros.parsear_estado(REGLAS, t), lambda t: filtros.parsear_moneda(REGLAS, t),
                  lambda t: filtros.parsear_fuente(REGLAS, t), filtros.parsear_monto, filtros.parsear_fecha):
            self.assertIsNone(f("   "))

    def test_valores_invalidos(self):
        casos = [(lambda: filtros.parsear_estado(REGLAS, "NADA"), "Estado no válido"),
                 (lambda: filtros.parsear_moneda(REGLAS, "XYZ"), "Moneda no soportada"),
                 (lambda: filtros.parsear_fuente(REGLAS, "fuente_Z"), "Fuente no reconocida"),
                 (lambda: filtros.parsear_monto("abc"), "Monto no válido"),
                 (lambda: filtros.parsear_monto("NaN"), "Monto no válido"),
                 (lambda: filtros.parsear_monto("Infinity"), "Monto no válido"),
                 (lambda: filtros.parsear_fecha("2025-13-45"), "Fecha no válida"),
                 (lambda: filtros.parsear_fecha("10/03/2025"), "Fecha no válida")]
        for llamada, texto in casos:
            with self.subTest(texto=texto):
                with self.assertRaises(ValueError) as ctx:
                    llamada()
                self.assertIn(texto, str(ctx.exception))


class TestConstruirFiltros(unittest.TestCase):
    def test_combinacion_valida(self):
        f, errores = filtros.construir_filtros(REGLAS, estado="success", moneda="usd", monto_min="1000",
                                               monto_max=5000, fecha_desde="2025-03-01")
        self.assertEqual(errores, [])
        self.assertEqual((f.estado, f.moneda, f.monto_min, f.monto_max, f.fecha_desde),
                         ("SUCCESS", "USD", D("1000"), D("5000"), "2025-03-01"))

    def test_none_se_ignora(self):
        f, errores = filtros.construir_filtros(REGLAS, estado=None, moneda=None)
        self.assertEqual((errores, f.activos()), ([], []))

    def test_se_informan_todos_los_errores_juntos(self):
        _, errores = filtros.construir_filtros(REGLAS, estado="NADA", moneda="XYZ", monto_min="abc", color="rojo", fuente=True)
        self.assertEqual(len(errores), 5)
        self.assertTrue(any("Criterio desconocido: 'color'" in e for e in errores))

    def test_rangos_invertidos(self):
        _, e1 = filtros.construir_filtros(REGLAS, monto_min=100, monto_max=10)
        _, e2 = filtros.construir_filtros(REGLAS, fecha_desde="2025-03-12", fecha_hasta="2025-03-01")
        self.assertIn("mínimo es mayor", e1[0])
        self.assertIn("posterior", e2[0])


class TestPresentacion(unittest.TestCase):
    def test_dinero(self):
        self.assertEqual(pres.dinero(D("1234.5")), "1,234.50")
        self.assertEqual(pres.dinero(D("40")), "40.00")

    def test_corto(self):
        self.assertEqual(pres.corto("abc", 10), "abc")
        self.assertEqual(pres.corto("abcdefghijklmnop", 10), "abcdefg...")

    def test_tabla_y_totales(self):
        r = procesar_archivo(ruta_datos("transacciones_validas.json"), REGLAS)
        tabla = pres.tabla_tx(r.valid[:3])
        self.assertEqual(len(tabla), 2 + 3)                      # encabezado + separador + filas
        self.assertIn("tx_001", tabla[2])
        totales = pres.totales_por_moneda(r.valid)
        self.assertEqual(totales, {"USD": D("7885.56"), "EUR": D("201.23"), "GBP": D("84.98")})
        self.assertEqual(pres.texto_totales(totales), "EUR 201.23  GBP 84.98  USD 7,885.56")


class TestExportacion(unittest.TestCase):
    def setUp(self):
        self.r = procesar_archivo(ruta_datos("transacciones_con_errores.json"), REGLAS)

    def test_contenido(self):
        c = exportacion.armar_contenido(self.r, REGLAS)
        self.assertEqual(set(c), set(exportacion.NOMBRES))
        self.assertEqual((len(c["normalizadas.json"]), len(c["invalidas.json"])), (7, 17))
        self.assertEqual(c["metricas.json"]["por_moneda"]["USD"]["total"], 2270.0)

    def test_escribir_y_detectar_existentes(self):
        with tempfile.TemporaryDirectory() as tmp:
            destino = os.path.join(tmp, "sub", "salida")
            self.assertEqual(exportacion.archivos_existentes(destino, exportacion.NOMBRES), [])
            rutas = exportacion.escribir(destino, exportacion.armar_contenido(self.r, REGLAS))
            self.assertEqual(len(rutas), 3)
            self.assertEqual(sorted(exportacion.archivos_existentes(destino, exportacion.NOMBRES)), sorted(exportacion.NOMBRES))
            with open(os.path.join(destino, "invalidas.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)[0]["posicion"], 2)

    def test_error_de_escritura_se_propaga(self):
        with tempfile.TemporaryDirectory() as tmp:
            archivo = os.path.join(tmp, "ocupado")
            open(archivo, "w").close()
            with self.assertRaises(OSError):
                exportacion.escribir(os.path.join(archivo, "dentro"), {"a.json": []})


if __name__ == "__main__":
    unittest.main()
