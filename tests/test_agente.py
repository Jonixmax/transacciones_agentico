"""Pruebas del agente completo: personalización, derivación, confirmación de efectos y guardas de seguridad."""
import os
import tempfile
import unittest

import helpers
from agentes.agente import Agente
from agentes.config_agentes import ConfigAgente
from agentes.skills import cargar_skills
from helpers import ClienteFalso


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.eco = helpers.crear_ecosistema("transacciones_con_errores.json", salida=self.tmp.name)
        self.analista, self.auditor = self.eco.agentes["analista"], self.eco.agentes["auditor"]

    def tearDown(self):
        self.tmp.cleanup()

    def carpeta(self, nombre="salida_agente"):
        return os.path.join(self.tmp.name, nombre)

    def con_cliente(self, cliente, agente="analista", politica="siempre"):
        return Agente(self.eco.configs[agente], self.eco.registro, cliente, self.eco.sesion, politica, self.eco.configs)


class TestPersonalizacion(Base):
    def test_saludos_distintos_por_configuracion(self):
        a, b = self.analista.atender("hola").texto, self.auditor.atender("hola").texto
        self.assertIn("Hola, soy Analista", a)
        self.assertIn("Mi objetivo es responder consultas", a)
        self.assertIn("Buen día, soy Auditor", b)
        self.assertIn("Mi objetivo es explicar por qué", b)

    def test_respuestas_con_el_estilo_de_cada_agente(self):
        a = self.analista.atender("cuántas transacciones exitosas en dólares")
        self.assertEqual((a.estado, a.skill), ("ok", "consulta-transacciones"))
        self.assertTrue(a.texto.startswith("[Analista]"))
        self.assertIn("4 de 7", a.texto)
        self.assertNotIn("Recomendación", a.texto)
        b = self.auditor.atender("resumen de las inválidas")
        self.assertTrue(b.texto.startswith("[Auditor] Informe de calidad de datos"))
        self.assertIn("Recomendación:", b.texto)
        self.assertIn("17 de 24", b.texto)

    def test_cambiar_la_configuracion_cambia_el_comportamiento_sin_tocar_codigo(self):
        antes = self.analista.atender("busca el id e_002").texto
        self.assertNotIn("Sugerencia:", antes)
        self.eco.configs["analista"].respuesta["mostrar_recomendacion"] = True
        despues = self.analista.atender("busca el id e_002").texto
        self.assertIn("Sugerencia: Pide al agente Auditor", despues)

    def test_ayuda_lista_solo_las_skills_del_agente(self):
        ayuda = self.analista.atender("ayuda").texto
        self.assertIn("consulta-transacciones", ayuda)
        self.assertIn("exportar-reporte", ayuda)
        self.assertIn("pide confirmación", ayuda)
        self.assertNotIn("diagnostico-invalidas", ayuda)

    def test_el_prompt_estructurado_y_la_divulgacion_progresiva(self):
        p = self.analista.prompt_sistema()
        for seccion in ("# ROL", "# OBJETIVO", "# TONO", "# REGLAS DE COMPORTAMIENTO", "# SKILLS DISPONIBLES",
                        "# POLÍTICA DE EFECTOS", "# FORMATO DE RESPUESTA"):
            self.assertIn(seccion, p)
        self.assertIn("consulta-transacciones", p)
        self.assertNotIn("diagnostico-invalidas", p)               # no es de este agente
        self.assertNotIn("## Pasos", p)                            # las instrucciones completas NO van en el prompt
        self.assertIn("Confirmación antes de escribir archivos: siempre", p)

    def test_las_skills_cargan_sus_instrucciones_solo_al_usarse(self):
        eco = helpers.crear_ecosistema("transacciones_con_errores.json")
        cargadas = lambda: sorted(s.nombre for s in eco.registro.todas() if s.instrucciones_cargadas)
        self.assertEqual(cargadas(), [])
        eco.agentes["analista"].atender("hola")
        self.assertEqual(cargadas(), [])
        eco.agentes["analista"].atender("lista las transacciones exitosas")
        self.assertEqual(cargadas(), ["consulta-transacciones"])
        eco.agentes["auditor"].atender("resumen de las inválidas")
        self.assertEqual(cargadas(), ["consulta-transacciones", "diagnostico-invalidas"])


class TestDerivacion(Base):
    def test_el_analista_deriva_al_auditor_sin_ejecutar(self):
        r = self.analista.atender("por qué se rechazaron los registros inválidos")
        self.assertEqual((r.estado, r.skill), ("fuera_de_alcance", "diagnostico-invalidas"))
        self.assertIn("/agente auditor", r.texto)
        self.assertFalse(self.eco.registro.get("diagnostico-invalidas").instrucciones_cargadas)

    def test_el_auditor_deriva_al_analista(self):
        r = self.auditor.atender("lista las transacciones exitosas")
        self.assertEqual(r.estado, "fuera_de_alcance")
        self.assertIn("/agente analista", r.texto)

    def test_mensajes_vacios_y_no_entendidos(self):
        for texto in ("", "   ", None, "cuál es la capital de Francia"):
            self.assertEqual(self.analista.atender(texto).estado, "no_entendido", repr(texto))

    def test_sin_datos(self):
        eco = helpers.crear_ecosistema()
        r = eco.agentes["analista"].atender("lista las transacciones")
        self.assertEqual(r.estado, "sin_datos")
        self.assertIn("/cargar", r.texto)


class TestConfirmacionDeEfectos(Base):
    def test_exportar_pide_confirmacion_y_no_escribe_antes(self):
        r = self.analista.atender("exporta el reporte")
        self.assertEqual((r.estado, r.skill), ("necesita_confirmacion", "exportar-reporte"))
        self.assertIn("¿Confirmas? (s/n)", r.texto)
        self.assertIn("4 archivos", r.texto)
        self.assertTrue(self.analista.pendiente)
        self.assertFalse(os.path.exists(self.carpeta()))

    def test_cancelar_no_escribe_nada(self):
        self.analista.atender("exporta el reporte")
        r = self.analista.confirmar(False)
        self.assertEqual(r.estado, "cancelado")
        self.assertIn("No se escribió nada", r.texto)
        self.assertFalse(self.analista.pendiente)
        self.assertFalse(os.path.exists(self.carpeta()))

    def test_confirmar_escribe_los_archivos(self):
        self.auditor.atender("exporta el reporte en la carpeta informe")
        r = self.auditor.confirmar(True)
        self.assertEqual(r.estado, "ok")
        self.assertEqual(sorted(os.listdir(self.carpeta("informe"))),
                         ["invalidas.json", "metricas.json", "normalizadas.json", "reporte.md"])

    def test_confirmar_sin_nada_pendiente(self):
        r = self.analista.confirmar(True)
        self.assertIn("No hay ninguna acción pendiente", r.texto)
        self.assertFalse(os.path.exists(self.carpeta()))

    def test_un_mensaje_nuevo_cancela_la_confirmacion_abierta(self):
        self.analista.atender("exporta el reporte")
        self.analista.atender("hola")
        self.assertFalse(self.analista.pendiente)
        self.analista.confirmar(True)
        self.assertFalse(os.path.exists(self.carpeta()))

    def test_no_se_puede_confirmar_dos_veces(self):
        self.analista.atender("exporta el reporte")
        self.analista.confirmar(True)
        self.assertIn("No hay ninguna acción pendiente", self.analista.confirmar(True).texto)

    def test_traza_conserva_los_pasos_previos(self):
        self.analista.atender("exporta el reporte")
        r = self.analista.confirmar(False)
        texto = " | ".join(r.trazas)
        self.assertIn("decisión", texto)
        self.assertIn("política", texto)
        self.assertIn("canceló", texto)

    def test_politica_nunca_ejecuta_directamente(self):
        ag = self.con_cliente(self.eco.agentes["analista"].cliente, politica="nunca")
        r = ag.atender("exporta el reporte")
        self.assertEqual(r.estado, "ok")
        self.assertTrue(os.path.exists(os.path.join(self.carpeta(), "reporte.md")))

    def test_politica_solo_sobrescribir(self):
        ag = self.con_cliente(self.eco.agentes["analista"].cliente, politica="solo_sobrescribir")
        self.assertEqual(ag.atender("exporta el reporte").estado, "ok")                       # no existía: sin pregunta
        self.assertEqual(ag.atender("exporta el reporte").estado, "necesita_confirmacion")    # ahora sobrescribiría
        self.assertIn("Se sobrescribirán", ag.atender("exporta el reporte").texto)


class TestGuardas(Base):
    """Un modelo que se equivoca o es manipulado no puede hacer que el agente haga lo que no debe."""

    def error(self, accion, agente="analista"):
        r = self.con_cliente(ClienteFalso(accion), agente).atender("lo que sea")
        self.assertEqual(r.estado, "error", accion)
        return r.texto

    def test_acciones_mal_formadas(self):
        for accion in (None, {}, [], "skill", {"accion": "hackear"}, {"skill": "consulta-transacciones"}):
            with self.subTest(accion=accion):
                self.assertIn("No ejecuté nada", self.error(accion))

    def test_skill_inexistente(self):
        self.assertIn("no existe", self.error({"accion": "skill", "skill": "borrar-todo", "args": {}}))

    def test_skill_no_permitida_para_el_agente(self):
        self.assertIn("no está permitida", self.error({"accion": "skill", "skill": "diagnostico-invalidas", "args": {}}))
        self.assertIn("no está permitida", self.error({"accion": "skill", "skill": "consulta-transacciones", "args": {}}, "auditor"))

    def test_argumentos_no_declarados_o_de_tipo_incorrecto(self):
        base = {"accion": "skill", "skill": "consulta-transacciones"}
        self.assertIn("no declarado", self.error({**base, "args": {"borrar": "todo"}}))
        self.assertIn("debe ser de tipo texto", self.error({**base, "args": {"estado": 5}}))
        self.assertIn("debe ser de tipo texto_o_numero", self.error({**base, "args": {"monto_min": [1]}}))
        self.assertIn("debe ser de tipo texto_o_numero", self.error({**base, "args": {"monto_min": True}}))
        self.assertIn("'args' debe ser un objeto", self.error({**base, "args": "x"}))
        self.assertIn("debe ser de tipo entero", self.error({"accion": "skill", "skill": "diagnostico-invalidas",
                                                             "args": {"posicion": "siete"}}, "auditor"))

    def test_fuera_de_alcance_con_skill_falsa(self):
        self.assertIn("skill existente", self.error({"accion": "fuera_de_alcance", "skill": "inventada"}))

    def test_el_modelo_no_puede_saltarse_la_confirmacion(self):
        ag = self.con_cliente(ClienteFalso({"accion": "skill", "skill": "exportar-reporte", "args": {"confirmado": True}}))
        self.assertIn("no declarado", ag.atender("x").texto)              # no existe ningún argumento "confirmado"
        ag = self.con_cliente(ClienteFalso({"accion": "skill", "skill": "exportar-reporte", "args": {}}))
        r = ag.atender("x")
        self.assertEqual(r.estado, "necesita_confirmacion")                # la política la aplica el agente
        self.assertFalse(os.path.exists(self.carpeta()))

    def test_rutas_peligrosas_se_rechazan_antes_de_pedir_confirmacion(self):
        for carpeta in ("/etc", "../afuera", "a/../../b", "~/x", "C:\\x"):
            with self.subTest(carpeta=carpeta):
                ag = self.con_cliente(ClienteFalso({"accion": "skill", "skill": "exportar-reporte", "args": {"carpeta": carpeta}}))
                r = ag.atender("x")
                self.assertEqual(r.estado, "error")
                self.assertFalse(ag.pendiente)
        self.assertEqual(os.listdir(self.tmp.name), [])                   # no se creó nada

    def test_si_el_modelo_falla_el_agente_no_se_cae(self):
        r = self.con_cliente(ClienteFalso(error=RuntimeError("sin conexión"))).atender("x")
        self.assertEqual(r.estado, "error")
        self.assertIn("sin conexión", r.texto)

    def test_si_una_skill_falla_el_agente_no_se_cae(self):
        with tempfile.TemporaryDirectory() as raiz:
            d = os.path.join(raiz, "skill-rota")
            os.makedirs(d)
            with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
                f.write("---\nname: skill-rota\ndescription: Una skill de prueba que siempre falla al ejecutarse.\nmetadata:\n  palabras_clave: rota\n---\nInstrucciones.")
            with open(os.path.join(d, "skill.py"), "w", encoding="utf-8") as f:
                f.write("PARAMETROS = {}\n\ndef ejecutar(sesion, **a):\n    raise RuntimeError('explotó')\n")
            registro = cargar_skills(raiz)
            cfg = ConfigAgente("t", "Test", "agente de prueba", "probar", "neutro", [], ["skill-rota"],
                               {"prefijo": "", "cierre": "", "mostrar_recomendacion": False, "etiqueta_recomendacion": ""},
                               {k: "x" for k in ("saludo", "fuera_de_alcance", "no_entendido", "sin_datos", "aclarar", "cancelado")})
            ag = Agente(cfg, registro, ClienteFalso({"accion": "skill", "skill": "skill-rota", "args": {}}),
                        self.eco.sesion, "siempre")
            r = ag.atender("x")
            self.assertEqual((r.estado, r.skill), ("error", "skill-rota"))
            self.assertIn("falló", r.texto)
            self.assertIn("explotó", r.texto)


class TestHistorialYTrazas(Base):
    def test_historial_y_traza(self):
        self.analista.atender("lista las transacciones exitosas")
        roles = [m["rol"] for m in self.analista.historial]
        self.assertEqual(roles, ["usuario", "skill", "agente"])           # las instrucciones de la skill entran al contexto
        traza = " | ".join(self.analista.ultima_traza)
        self.assertIn("decisión", traza)
        self.assertIn("skill: consulta-transacciones", traza)
        self.assertIn("observación", traza)

    def test_configuracion_de_otro_agente_con_mensaje_desconocido_no_rompe(self):
        self.eco.configs["analista"].mensajes["saludo"] = "Hola {nombre} {campo_inexistente}"
        self.assertIn("{campo_inexistente}", self.analista.atender("hola").texto)


if __name__ == "__main__":
    unittest.main()
