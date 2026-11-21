"""Pruebas del chat y del punto de entrada simulando lo que escribiría el usuario."""
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

import helpers
import main as programa
from agentes.config_agentes import ConfigError
from chat_agente import Chat


def conversar(entradas, ruta=None, salida_dir=None, agente="analista"):
    """Ejecuta el chat con respuestas predefinidas. Devuelve (todo lo mostrado, ecosistema)."""
    eco = helpers.crear_ecosistema(salida=salida_dir)
    it = iter(entradas)

    mostrado = []

    def entrada(prompt):
        mostrado.append(prompt)             # un prompt de input() también es algo que el usuario ve
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    Chat(eco, agente, entrada=entrada, salida=mostrado.append).ejecutar(ruta)
    return "\n".join(mostrado), eco


ERRORES = helpers.ruta_datos("transacciones_con_errores.json")
VALIDAS = helpers.ruta_datos("transacciones_validas.json")


class TestChat(unittest.TestCase):
    def test_conversacion_con_el_analista(self):
        out, _ = conversar(["lista las transacciones exitosas", "/salir"], VALIDAS)
        self.assertIn("Archivo cargado: 12 registros (12 válidos, 0 inválidos)", out)
        self.assertIn("Hola, soy Analista", out)
        self.assertIn("6 transacciones válidas cumplen: estado: SUCCESS", out)
        self.assertIn("Hasta luego", out)

    def test_cambiar_de_agente(self):
        out, _ = conversar(["/agente", "/agente auditor", "resumen de las inválidas", "/agente fantasma", "/salir"], ERRORES)
        self.assertIn("analista: analista de transacciones  <- actual", out)
        self.assertIn("Ahora hablas con Auditor", out)
        self.assertIn("Se rechazaron 17 de 24", out)
        self.assertIn("No existe el agente 'fantasma'", out)

    def test_arrancar_con_otro_agente(self):
        out, _ = conversar(["/salir"], ERRORES, agente="auditor")
        self.assertIn("Buen día, soy Auditor", out)
        with self.assertRaises(ValueError):
            Chat(helpers.crear_ecosistema(), "inexistente")

    def test_comandos_de_informacion(self):
        out, _ = conversar(["/traza", "/skills", "/prompt", "/ayuda", "/comando_raro", "/salir"], VALIDAS)
        self.assertIn("(todavía no hay trazas)", out)
        self.assertIn("consulta-transacciones  [solo lectura]  agentes: analista", out)
        self.assertIn("exportar-reporte  [escribe archivos]  agentes: analista, auditor", out)
        self.assertIn("# ROL", out)
        self.assertIn("/cargar [archivo]", out)
        self.assertIn("Comando desconocido: /comando_raro", out)

    def test_traza_despues_de_una_consulta(self):
        out, _ = conversar(["cuántas transacciones en euros", "/traza", "/salir"], VALIDAS)
        self.assertIn("skill: consulta-transacciones", out)

    def test_exportar_con_confirmacion_afirmativa(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = conversar(["exporta el reporte", "s", "/salir"], VALIDAS, salida_dir=tmp)
            self.assertIn("¿Confirmas? (s/n)", out)
            self.assertIn("Listo: escribí 4 archivos", out)
            self.assertTrue(os.path.isfile(os.path.join(tmp, "salida_agente", "reporte.md")))

    def test_exportar_cancelado(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = conversar(["exporta el reporte", "n", "/salir"], VALIDAS, salida_dir=tmp)
            self.assertIn("Acción cancelada", out)
            self.assertEqual(os.listdir(tmp), [])

    def test_respuesta_invalida_a_la_confirmacion_se_vuelve_a_pedir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, _ = conversar(["exporta el reporte", "quizás", "", "no", "/salir"], VALIDAS, salida_dir=tmp)
            self.assertEqual(out.count("Responde 's' o 'n'."), 2)
            self.assertEqual(os.listdir(tmp), [])

    def test_cargar_otro_archivo_pide_confirmacion(self):
        lista = helpers.ruta_datos("lista_vacia.json")
        out, eco = conversar([f"/cargar {lista}", "n", "/salir"], ERRORES)
        self.assertIn("¿Reemplazarlos con", out)
        self.assertIn("Carga cancelada. Se conservan los datos actuales.", out)
        self.assertEqual(eco.sesion.resultado.total, 24)
        out, eco = conversar([f"/cargar {lista}", "s", "/salir"], ERRORES)
        self.assertEqual(eco.sesion.resultado.total, 0)
        self.assertIn("Archivo cargado: 0 registros", out)

    def test_cargar_un_archivo_malo_conserva_los_datos(self):
        malo = helpers.ruta_datos("json_malformado.json")
        out, eco = conversar([f"/cargar {malo}", "s", "/salir"], ERRORES)
        self.assertIn("no es un JSON válido", out)
        self.assertEqual(eco.sesion.resultado.total, 24)
        self.assertEqual(eco.sesion.ruta, ERRORES)

    def test_cargar_sin_argumento_ofrece_los_archivos(self):
        out, eco = conversar(["/cargar", "1", "s", "/salir"], ERRORES)
        self.assertIn("ejemplo_enunciado.json", out)
        self.assertEqual(eco.sesion.resultado.total, 3)

    def test_elegir_archivo_al_iniciar(self):
        out, eco = conversar(["1", "/salir"])
        self.assertIn("Archivos de ejemplo en datos/", out)
        self.assertEqual(eco.sesion.resultado.total, 3)

    def test_archivo_inexistente_al_iniciar_permite_salir(self):
        out, eco = conversar([""], helpers.ruta_datos("no_existe.json"))
        self.assertIn("Error: no existe el archivo", out)
        self.assertIn("Hasta luego", out)
        self.assertFalse(eco.sesion.tiene_datos)

    def test_numero_fuera_de_rango_y_cierre_de_entrada(self):
        out, _ = conversar(["99", ""])
        self.assertIn("Número fuera de rango", out)
        out, _ = conversar([], VALIDAS)
        self.assertIn("Hasta luego", out)

    def test_sin_datos_pide_cargar(self):
        # el chat no deja conversar sin datos: obliga a elegir archivo antes
        out, eco = conversar(["1", "lista las transacciones", "/salir"])
        self.assertTrue(eco.sesion.tiene_datos)


class TestMain(unittest.TestCase):
    def test_agente_desconocido(self):
        with mock.patch("builtins.print") as p:
            self.assertEqual(programa.main(["--agente", "fantasma", VALIDAS]), 1)
        self.assertIn("no existe el agente 'fantasma'", p.call_args[0][0])

    def test_agente_sin_nombre(self):
        with mock.patch("builtins.print") as p:
            self.assertEqual(programa.main(["--agente"]), 1)
        self.assertIn("necesita un nombre", p.call_args[0][0])

    def test_error_de_configuracion_se_informa_con_claridad(self):
        with mock.patch("main.fabrica.construir", side_effect=ConfigError("falta 'rol'")):
            with mock.patch("builtins.print") as p:
                self.assertEqual(programa.main([VALIDAS]), 1)
        self.assertIn("Error de configuración: falta 'rol'", p.call_args[0][0])

    def test_modo_chat_completo_por_entrada_estandar(self):
        with mock.patch("builtins.input", side_effect=["/salir"]):
            with mock.patch("builtins.print"):
                self.assertEqual(programa.main([VALIDAS]), 0)

    def test_modo_clasico_sigue_funcionando(self):
        salida = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("1\n0\n")), contextlib.redirect_stdout(salida):
            self.assertEqual(programa.main(["clasico", VALIDAS]), 0)
        self.assertIn("Total procesadas ..... 12", salida.getvalue())


if __name__ == "__main__":
    unittest.main()
