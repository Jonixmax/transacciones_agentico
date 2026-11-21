"""Pruebas de cada skill ejecutada directamente. Valores esperados calculados a mano de los archivos de datos."""
import json
import os
import tempfile
import unittest

import helpers
from agentes.skills import ResultadoSkill
from nucleo.modelos import InvalidRecord

ECO = helpers.crear_ecosistema()
CONSULTA = ECO.registro.get("consulta-transacciones")
DIAG = ECO.registro.get("diagnostico-invalidas")
EXPORT = ECO.registro.get("exportar-reporte")


def ids(res):
    return set(res.datos["ids"])


class TestConsulta(unittest.TestCase):
    def setUp(self):
        self.s = helpers.crear_sesion("transacciones_validas.json")

    def test_filtros_simples(self):
        casos = [
            (dict(estado="SUCCESS"), {"tx_001", "tx_004", "tx_005", "204", "207", "A-77"}),
            (dict(moneda="EUR"), {"tx_003", "205", "A-77"}),
            (dict(monto_min="1000"), {"tx_004", "206", "A-78"}),
            (dict(monto_max="50"), {"tx_005", "205", "207", "A-79"}),
            (dict(estado="PENDING", fuente="fuente_B"), {"205"}),
            (dict(moneda="GBP", estado="FAILED"), {"A-79"}),
            (dict(estado="SUCCESS", moneda="USD"), {"tx_001", "tx_004", "204"}),
        ]
        for criterios, esperado in casos:
            with self.subTest(criterios=criterios):
                self.assertEqual(ids(CONSULTA.ejecutar(self.s, **criterios)), esperado)

    def test_fechas_inclusivas(self):
        desde = CONSULTA.ejecutar(self.s, fecha_desde="2025-03-12")
        hasta = CONSULTA.ejecutar(self.s, fecha_hasta="2025-03-11")
        self.assertEqual(ids(desde), {"tx_003", "tx_004", "tx_005", "206", "207", "A-79"})
        self.assertEqual(ids(hasta), {"tx_001", "tx_002", "204", "205", "A-77", "A-78"})
        # un solo día completo: A-78 es 2025-03-11T08:00Z (venía como 10:00+02:00)
        self.assertIn("A-78", ids(CONSULTA.ejecutar(self.s, fecha_desde="2025-03-11", fecha_hasta="2025-03-11")))

    def test_los_limites_de_monto_son_inclusivos(self):
        self.assertIn("A-79", ids(CONSULTA.ejecutar(self.s, monto_max="45")))
        self.assertIn("A-79", ids(CONSULTA.ejecutar(self.s, monto_min="45", monto_max="45")))

    def test_contar(self):
        r = CONSULTA.ejecutar(self.s, operacion="contar", moneda="EUR")
        self.assertTrue(r.ok)
        self.assertIn("3 de 12", r.texto)

    def test_totales(self):
        r = CONSULTA.ejecutar(self.s, operacion="totales", moneda="USD")
        self.assertEqual(r.datos["por_moneda"]["USD"], {"cantidad": 6, "total": "7885.56", "confirmado": "1401.00"})
        self.assertIn("7,885.56", r.texto)
        self.assertIn("1,401.00", r.texto)
        todo = CONSULTA.ejecutar(self.s, operacion="totales")
        self.assertEqual(set(todo.datos["por_moneda"]), {"USD", "EUR", "GBP"})        # no se mezclan monedas
        self.assertEqual(todo.datos["por_moneda"]["EUR"]["total"], "201.23")

    def test_listar_respeta_el_limite_de_filas(self):
        self.s.max_filas = 3
        r = CONSULTA.ejecutar(self.s)
        self.assertEqual((r.datos["coincidencias"], r.datos["mostradas"]), (12, 3))
        self.assertIn("primeras 3 de 12", r.texto)

    def test_sin_coincidencias(self):
        r = CONSULTA.ejecutar(self.s, moneda="GBP", estado="PENDING")
        self.assertTrue(r.ok)
        self.assertIn("No hay transacciones válidas que cumplan: estado: PENDING, moneda: GBP", r.texto)

    def test_criterios_invalidos_no_ejecutan_la_consulta(self):
        r = CONSULTA.ejecutar(self.s, estado="NADA", monto_min="abc")
        self.assertFalse(r.ok)
        self.assertIn("Estado no válido", r.texto)
        self.assertIn("Monto no válido", r.texto)
        self.assertNotIn("coincidencias", r.datos)
        self.assertFalse(CONSULTA.ejecutar(self.s, monto_min="100", monto_max="10").ok)

    def test_operacion_invalida(self):
        r = CONSULTA.ejecutar(self.s, operacion="borrar")
        self.assertFalse(r.ok)
        self.assertIn("Operación no válida", r.texto)

    def test_buscar(self):
        r = CONSULTA.ejecutar(self.s, operacion="buscar", id="a-77")        # sin distinguir mayúsculas
        self.assertTrue(r.ok)
        self.assertEqual(r.datos["ids"], ["A-77"])
        self.assertIn("99.99", r.texto)
        self.assertIn("€99,99", r.texto)                                    # registro original
        self.assertEqual(CONSULTA.ejecutar(self.s, operacion="buscar", id="204").datos["ids"], ["204"])
        self.assertFalse(CONSULTA.ejecutar(self.s, operacion="buscar").ok)
        self.assertIn("No hay ninguna transacción con id 'zzz'", CONSULTA.ejecutar(self.s, operacion="buscar", id="zzz").texto)

    def test_buscar_un_id_que_esta_entre_las_invalidas(self):
        s = helpers.crear_sesion("transacciones_con_errores.json")
        r = CONSULTA.ejecutar(s, operacion="buscar", id="e_002")
        self.assertIn("registro inválido #2", r.texto)
        self.assertIn("Auditor", r.recomendacion)
        # un id que existe como válido y también repetido como inválido: se encuentra el válido
        self.assertEqual(CONSULTA.ejecutar(s, operacion="buscar", id="e_001").datos["ids"], ["e_001"])


class TestDiagnostico(unittest.TestCase):
    def setUp(self):
        self.s = helpers.crear_sesion("transacciones_con_errores.json")

    def test_resumen(self):
        r = DIAG.ejecutar(self.s, operacion="resumen")
        self.assertEqual((r.datos["invalidas"], r.datos["tipos"]), (17, 13))
        self.assertEqual(r.datos["por_categoria"]["monto no numérico"], 2)
        self.assertEqual(r.datos["por_categoria"]["falta campo obligatorio"], 2)
        self.assertEqual(r.datos["por_categoria"]["id duplicado"], 1)
        self.assertEqual(sum(r.datos["por_categoria"].values()), 17)
        self.assertIn("17 de 24", r.texto)
        self.assertIn("70.8%", r.texto)
        self.assertIn("severidad alta", r.recomendacion)

    def test_detalle(self):
        r = DIAG.ejecutar(self.s, operacion="detalle", posicion=7)
        self.assertTrue(r.ok)
        self.assertIn("31/02/2025 10:30", r.texto)
        self.assertIn("Cómo corregirlo", r.texto)
        self.assertIn("formatos_fecha", r.texto)                            # viene de la guía
        self.assertEqual(r.datos["posicion"], 7)

    def test_detalle_de_una_posicion_valida_o_inexistente(self):
        r = DIAG.ejecutar(self.s, operacion="detalle", posicion=8)           # el registro 8 es válido
        self.assertFalse(r.ok)
        self.assertIn("#2", r.texto)
        self.assertFalse(DIAG.ejecutar(self.s, operacion="detalle", posicion=999).ok)

    def test_por_motivo(self):
        casos = {"fecha": [7, 13, 18], "duplicado": [10], "moneda": [4, 16, 22], "monto": [2, 5, 6, 12, 14],
                 "numerico": [2, 12], "campo": [3, 15], "objeto": [20]}
        for motivo, esperado in casos.items():
            with self.subTest(motivo=motivo):
                self.assertEqual(DIAG.ejecutar(self.s, motivo=motivo).datos["posiciones"], esperado)
        sin = DIAG.ejecutar(self.s, operacion="por_motivo", motivo="zzz")
        self.assertTrue(sin.ok)
        self.assertIn("No hay registros inválidos", sin.texto)
        self.assertFalse(DIAG.ejecutar(self.s, operacion="por_motivo").ok)

    def test_plan_agrupa_por_tipo_de_accion(self):
        r = DIAG.ejecutar(self.s, operacion="plan")
        self.assertEqual(r.datos["acciones"], {
            "corregir_dato": [2, 3, 7, 12, 14, 15, 16, 18, 22],
            "revisar_fuente": [5, 6, 10, 13, 21],
            "configurar_reglas": [4, 19],
            "descartar": [20],
        })
        self.assertEqual(list(r.datos["acciones"]), ["corregir_dato", "revisar_fuente", "configurar_reglas", "descartar"])
        self.assertEqual(sum(len(v) for v in r.datos["acciones"].values()), 17)
        self.assertIn("(1 registro)", r.texto)                               # singular correcto

    def test_la_operacion_se_infiere(self):
        self.assertIn("Registro #7", DIAG.ejecutar(self.s, posicion=7).texto)
        self.assertEqual(DIAG.ejecutar(self.s, motivo="fecha").datos["posiciones"], [7, 13, 18])
        self.assertEqual(DIAG.ejecutar(self.s).datos["invalidas"], 17)
        self.assertEqual(DIAG.ejecutar(self.s, operacion="detalle").datos["invalidas"], 17)   # sin número = resumen

    def test_operacion_invalida(self):
        self.assertFalse(DIAG.ejecutar(self.s, operacion="hackear").ok)

    def test_sin_invalidas_es_una_buena_noticia(self):
        r = DIAG.ejecutar(helpers.crear_sesion("transacciones_validas.json"))
        self.assertTrue(r.ok)
        self.assertIn("No hay registros inválidos", r.texto)

    def test_la_guia_cubre_todos_los_motivos_de_los_datos_de_prueba(self):
        guia = DIAG.recurso_json("guia_motivos.json")
        from nucleo.metricas import categoria_motivo
        categorias = {categoria_motivo(m) for inv in self.s.resultado.invalid for m in inv.reasons}
        self.assertEqual(categorias - set(guia["categorias"]), set())

    def test_la_guia_es_consistente(self):
        guia = DIAG.recurso_json("guia_motivos.json")
        for cat, e in list(guia["categorias"].items()) + [("otro", guia["otro"])]:
            for campo in ("titulo", "explicacion", "causa_probable", "correccion", "severidad", "accion"):
                self.assertTrue(e.get(campo), f"{cat}.{campo}")
            self.assertIn(e["severidad"], ("alta", "media", "baja"), cat)
            self.assertIn(e["accion"], guia["acciones"], cat)

    def test_categoria_sin_guia_usa_la_generica_sin_inventar(self):
        self.s.resultado.invalid.append(InvalidRecord(99, {"x": 1}, None, ["algo rarísimo: detalle"]))
        r = DIAG.ejecutar(self.s, operacion="detalle", posicion=99)
        self.assertTrue(r.ok)
        self.assertIn("no está en la guía", r.texto)              # lo dice, en lugar de inventar una explicación
        self.assertIn("No determinada", r.texto)


class TestExportar(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = helpers.crear_sesion("transacciones_con_errores.json", salida=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def destino(self, nombre="salida_agente"):
        return os.path.join(self.tmp.name, nombre)

    def test_previsualizar_no_escribe_nada(self):
        p = EXPORT.previsualizar(self.s)
        self.assertIn("4 archivos", p.texto)
        self.assertIn("salida_agente", p.texto)
        self.assertFalse(p.sobrescribe)
        self.assertFalse(os.path.exists(self.destino()))

    def test_ejecutar_escribe_los_cuatro_archivos(self):
        r = EXPORT.ejecutar(self.s)
        self.assertTrue(r.ok)
        self.assertEqual(sorted(os.listdir(self.destino())), ["invalidas.json", "metricas.json", "normalizadas.json", "reporte.md"])
        with open(os.path.join(self.destino(), "normalizadas.json"), encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)), 7)

    def test_contenido_del_reporte(self):
        EXPORT.ejecutar(self.s, carpeta="informe")
        with open(os.path.join(self.destino("informe"), "reporte.md"), encoding="utf-8") as f:
            md = f.read()
        for pedazo in ("**24** registros", "**7** válidos (29.2%)", "**17** inválidos", "| USD | 5 | 2,270.00 | 2,230.00 |",
                       "| EUR | 2 | 1,294.56 | 1,234.56 |", "- SUCCESS: 5", "- FAILED: 2", "- PENDING: 0",
                       "2 × monto no numérico", "e_008", "e_009", "**Archivo analizado:** transacciones_con_errores.json"):
            self.assertIn(pedazo, md)
        self.assertNotIn(helpers.RAIZ, md)                                 # no filtra rutas absolutas del equipo
        self.assertNotIn("{{", md)                                         # no quedó ningún marcador sin reemplazar

    def test_segunda_vez_avisa_que_sobrescribe(self):
        EXPORT.ejecutar(self.s)
        p = EXPORT.previsualizar(self.s)
        self.assertTrue(p.sobrescribe)
        self.assertIn("Se sobrescribirán", p.texto)

    def test_rutas_inseguras_se_rechazan(self):
        inseguras = ["/etc", "/tmp/afuera", "../fuera", "a/../../b", "..", "sub/../otra", "~/x", "C:\\datos", "\\\\servidor\\x", "   "]
        for carpeta in inseguras:
            with self.subTest(carpeta=carpeta):
                with self.assertRaises(ValueError):
                    EXPORT.previsualizar(self.s, carpeta=carpeta)
                r = EXPORT.ejecutar(self.s, carpeta=carpeta)              # defensa también en ejecutar
                self.assertFalse(r.ok)
                self.assertIn("No escribí nada", r.texto)

    def test_enlace_simbolico_que_escapa_se_rechaza(self):
        with tempfile.TemporaryDirectory() as afuera:
            try:
                os.symlink(afuera, os.path.join(self.tmp.name, "enlace"))
            except (OSError, NotImplementedError):
                self.skipTest("el sistema no permite enlaces simbólicos")
            with self.assertRaises(ValueError):
                EXPORT.previsualizar(self.s, carpeta="enlace")
            self.assertFalse(EXPORT.ejecutar(self.s, carpeta="enlace").ok)
            self.assertEqual(os.listdir(afuera), [])

    def test_error_de_escritura(self):
        open(os.path.join(self.tmp.name, "ocupado"), "w").close()
        r = EXPORT.ejecutar(self.s, carpeta="ocupado/dentro")
        self.assertFalse(r.ok)
        self.assertIn("No pude escribir", r.texto)


if __name__ == "__main__":
    unittest.main()
