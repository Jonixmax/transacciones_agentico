"""Pruebas del modo simulado: elección de skill, extracción de argumentos y casos fuera de alcance."""
import unittest
from unittest.mock import patch

import helpers
from agentes import llm
from agentes import skills as sk

REG = sk.cargar_skills(helpers.os.path.join(helpers.RAIZ, "skills"))
ANALISTA = REG.catalogo({"consulta-transacciones", "exportar-reporte"})
AUDITOR = REG.catalogo({"diagnostico-invalidas", "exportar-reporte"})
LLM = llm.ModoSimulado()


def decidir(texto, catalogo=ANALISTA):
    return LLM.decidir("", [{"rol": "usuario", "texto": texto}], catalogo)


class TestAnalista(unittest.TestCase):
    def comprobar(self, casos, skill="consulta-transacciones"):
        for texto, args in casos.items():
            with self.subTest(texto=texto):
                d = decidir(texto)
                self.assertEqual(d["accion"], "skill", d)
                self.assertEqual(d["skill"], skill)
                self.assertEqual(d["args"], args)

    def test_filtros_basicos(self):
        self.comprobar({
            "lista las transacciones exitosas": {"operacion": "listar", "estado": "SUCCESS"},
            "cuántas transacciones en euros hay": {"operacion": "contar", "moneda": "EUR"},
            "cuánto suman las transacciones en dólares": {"operacion": "totales", "moneda": "USD"},
            "transacciones pendientes de la fuente B": {"estado": "PENDING", "fuente": "fuente_b"},
            "fallidas en libras": {"estado": "FAILED", "moneda": "GBP"},
            "cuántas transacciones exitosas en dólares": {"operacion": "contar", "estado": "SUCCESS", "moneda": "USD"},
        })

    def test_montos(self):
        self.comprobar({
            "muestra las transacciones mayores a 1000": {"operacion": "listar", "monto_min": "1000"},
            "transacciones menores a 50": {"monto_max": "50"},
            "transacciones de no más de 50": {"monto_max": "50"},                # "no más de" NO es un mínimo
            "transacciones de al menos 100": {"monto_min": "100"},
        })

    def test_fechas_no_se_confunden_con_montos(self):
        self.comprobar({
            "transacciones desde 2025-03-12": {"fecha_desde": "2025-03-12"},
            "transacciones hasta 2025-03-11": {"fecha_hasta": "2025-03-11"},
            "transacciones entre 2025-03-10 y 2025-03-11": {"fecha_desde": "2025-03-10", "fecha_hasta": "2025-03-11"},
            "transacciones del 10/03/2025": {"fecha_desde": "2025-03-10", "fecha_hasta": "2025-03-10"},
            "transacciones del 2025-03-10": {"fecha_desde": "2025-03-10", "fecha_hasta": "2025-03-10"},
        })

    def test_busqueda_por_id(self):
        self.comprobar({
            "busca el id A-77": {"operacion": "buscar", "id": "a-77"},
            "busca la transacción 204": {"operacion": "buscar", "id": "204"},
            "detalle de tx_001": {"operacion": "buscar", "id": "tx_001"},
        })

    def test_exportar(self):
        self.comprobar({"exporta el reporte": {},
                        "exporta el reporte en la carpeta resultados": {"carpeta": "resultados"},
                        "genera un informe": {}}, skill="exportar-reporte")

    def test_mayusculas_y_acentos_no_importan(self):
        self.assertEqual(decidir("LISTA LAS TRANSACCIONES EXITOSAS"), decidir("lista las transacciones exitosas"))
        self.assertEqual(decidir("CUÁNTAS transacciones EN EUROS")["args"], {"operacion": "contar", "moneda": "EUR"})

    def test_lo_que_no_es_suyo_se_deriva(self):
        for texto in ("por qué se rechazaron los registros inválidos", "plan de corrección", "explica el registro 7"):
            with self.subTest(texto=texto):
                d = decidir(texto)
                self.assertEqual(d, {"accion": "fuera_de_alcance", "skill": "diagnostico-invalidas"})


class TestAuditor(unittest.TestCase):
    def test_operaciones(self):
        casos = {
            "resumen de los registros inválidos": {"operacion": "resumen"},
            "explica el registro 7": {"operacion": "detalle", "posicion": 7},
            "explícame el registro #12": {"operacion": "detalle", "posicion": 12},
            "qué registros tienen problemas de fecha": {"motivo": "fecha"},
            "hay registros duplicados": {"motivo": "duplicado"},
            "plan de corrección": {"operacion": "plan"},
        }
        for texto, args in casos.items():
            with self.subTest(texto=texto):
                d = decidir(texto, AUDITOR)
                self.assertEqual((d["accion"], d["skill"], d["args"]), ("skill", "diagnostico-invalidas", args))

    def test_lo_de_transacciones_validas_se_deriva_al_analista(self):
        for texto in ("lista las transacciones exitosas", "cuánto suman las transacciones en dólares"):
            self.assertEqual(decidir(texto, AUDITOR), {"accion": "fuera_de_alcance", "skill": "consulta-transacciones"})


class TestOtrosCasos(unittest.TestCase):
    def test_saludo_y_ayuda(self):
        self.assertEqual(decidir("hola")["accion"], "saludo")
        self.assertEqual(decidir("Buenas")["accion"], "saludo")
        for texto in ("ayuda", "¿qué puedes hacer?", "help"):
            self.assertEqual(decidir(texto)["accion"], "ayuda", texto)

    def test_no_entendido(self):
        for texto in ("", "   ", "xyz qwerty", "?????", "cuál es la capital de Francia"):
            self.assertEqual(decidir(texto)["accion"], "no_entendido", repr(texto))

    def test_empate_entre_skills_permitidas_pide_aclarar(self):
        def entrada(nombre):
            return {"nombre": nombre, "descripcion": "descripcion generica de prueba", "parametros": {},
                    "palabras_clave": ["cosa"], "vocabulario": {}, "permitida": True}
        d = decidir("quiero una cosa", [entrada("skill-uno"), entrada("skill-dos")])
        self.assertEqual(d, {"accion": "aclarar", "opciones": ["skill-uno", "skill-dos"]})

    def test_sin_skills_permitidas_siempre_deriva(self):
        todo_ajeno = REG.catalogo(set())
        self.assertEqual(decidir("lista las transacciones", todo_ajeno)["accion"], "fuera_de_alcance")

    def test_decidir_es_determinista(self):
        self.assertEqual([decidir("cuántas transacciones en euros") for _ in range(5)],
                         [decidir("cuántas transacciones en euros")] * 5)

    def test_toma_el_ultimo_mensaje_del_usuario(self):
        historial = [{"rol": "usuario", "texto": "lista las transacciones"}, {"rol": "agente", "texto": "..."},
                     {"rol": "usuario", "texto": "cuántas en euros"}]
        self.assertEqual(LLM.decidir("", historial, ANALISTA)["args"]["moneda"], "EUR")

    def test_redactar_aplica_la_configuracion_del_agente(self):
        res = sk.ResultadoSkill(True, "cuerpo", recomendacion="haz esto")
        formal = LLM.redactar("", [], res, {"prefijo": "[Auditor]", "cierre": "Fin.", "mostrar_recomendacion": True,
                                            "etiqueta_recomendacion": "Recomendación"})
        conciso = LLM.redactar("", [], res, {"prefijo": "", "cierre": "", "mostrar_recomendacion": False})
        self.assertEqual(formal, "[Auditor]\ncuerpo\nRecomendación: haz esto\nFin.")
        self.assertEqual(conciso, "cuerpo")

    def test_la_interfaz_base_no_esta_implementada(self):
        with self.assertRaises(NotImplementedError):
            llm.ClienteLLM().decidir("", [], [])
        with self.assertRaises(NotImplementedError):
            llm.ClienteLLM().redactar("", [], None, {})


class TestClienteGemini(unittest.TestCase):
    def test_exige_clave(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ValueError):
                llm.ClienteGemini()

    def test_modelo_predeterminado(self):
        with patch.dict("os.environ", {"GEMINI_API_KEY": "clave-prueba"}, clear=True):
            self.assertEqual(llm.ClienteGemini().model, "gemini-3.8-flash")

    def test_decidir_lee_json_de_gemini(self):
        cliente = llm.ClienteGemini(api_key="clave-prueba")
        respuesta = '{"accion":"skill","skill":"consulta-transacciones","args":{"operacion":"contar"}}'
        with patch.object(cliente, "_solicitar", return_value="```json\n" + respuesta + "\n```"):
            accion = cliente.decidir("prompt", [{"rol": "usuario", "texto": "cuántas hay"}], [])
        self.assertEqual(accion["skill"], "consulta-transacciones")
        self.assertEqual(accion["args"]["operacion"], "contar")

    def test_rechaza_json_invalido(self):
        cliente = llm.ClienteGemini(api_key="clave-prueba")
        with self.assertRaises(ValueError):
            cliente._json("esto no es json")


if __name__ == "__main__":
    unittest.main()
