"""Pruebas del cargador de skills y de la configuración de agentes: validación estricta de lo que se carga."""
import json
import os
import tempfile
import unittest

import helpers
from agentes import config_agentes as ca
from agentes import skills as sk

SKILLS = os.path.join(helpers.RAIZ, "skills")
DESC = "Una descripción de prueba suficientemente larga para pasar la validación."
PY_OK = "PARAMETROS = {}\n\ndef ejecutar(sesion, **args):\n    return None\n"


def crear_skill(raiz, nombre, md=None, py=PY_OK, carpeta=None):
    d = os.path.join(raiz, carpeta or nombre)
    os.makedirs(d)
    if md is None:
        md = f"---\nname: {nombre}\ndescription: {DESC}\nmetadata:\n  palabras_clave: prueba\n  efectos: ninguno\n---\n# Título\nInstrucciones.\n"
    if md is not False:
        with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(md)
    if py is not None:
        with open(os.path.join(d, "skill.py"), "w", encoding="utf-8") as f:
            f.write(py)
    return d


class TestSkillsReales(unittest.TestCase):
    def test_cargan_las_tres_skills(self):
        reg = sk.cargar_skills(SKILLS)
        self.assertEqual(sorted(reg.nombres()), ["consulta-transacciones", "diagnostico-invalidas", "exportar-reporte"])

    def test_efectos_y_confirmacion(self):
        reg = sk.cargar_skills(SKILLS)
        self.assertTrue(reg.get("exportar-reporte").requiere_confirmacion)
        self.assertFalse(reg.get("consulta-transacciones").requiere_confirmacion)
        self.assertFalse(reg.get("diagnostico-invalidas").requiere_confirmacion)

    def test_cada_skill_tiene_los_recursos_documentados(self):
        for nombre, recursos in {"consulta-transacciones": ["vocabulario.json"],
                                 "diagnostico-invalidas": ["guia_motivos.json", "vocabulario.json"],
                                 "exportar-reporte": ["plantilla_reporte.md"]}.items():
            for r in recursos:
                self.assertTrue(os.path.isfile(os.path.join(SKILLS, nombre, "recursos", r)), f"{nombre}/{r}")

    def test_divulgacion_progresiva(self):
        reg = sk.cargar_skills(SKILLS)
        self.assertEqual([s.nombre for s in reg.todas() if s.instrucciones_cargadas], [])
        s = reg.get("consulta-transacciones")
        texto = s.instrucciones()
        self.assertTrue(s.instrucciones_cargadas)
        self.assertIn("## Pasos", texto)
        self.assertNotIn("name:", texto)                       # el cuerpo no incluye los metadatos
        self.assertFalse(reg.get("diagnostico-invalidas").instrucciones_cargadas)

    def test_catalogo_marca_las_permitidas(self):
        reg = sk.cargar_skills(SKILLS)
        cat = {e["nombre"]: e["permitida"] for e in reg.catalogo({"consulta-transacciones"})}
        self.assertEqual(cat, {"consulta-transacciones": True, "diagnostico-invalidas": False, "exportar-reporte": False})

    def test_descripciones_dentro_del_limite(self):
        for s in sk.cargar_skills(SKILLS).todas():
            self.assertTrue(20 <= len(s.descripcion) <= 1024, s.nombre)


class TestFrontmatter(unittest.TestCase):
    def test_parseo(self):
        meta, cuerpo = sk.parsear_frontmatter("---\nname: a\ndescription: b c\n---\n\n# Hola\ncuerpo")
        self.assertEqual(meta, {"name": "a", "description": "b c"})
        self.assertEqual(cuerpo, "# Hola\ncuerpo")

    def test_bloque_anidado_metadata(self):
        meta, _ = sk.parsear_frontmatter("---\nname: a\nmetadata:\n  k1: v1\n  k2: v2, v3\n---\ncuerpo")
        self.assertEqual(meta["metadata"], {"k1": "v1", "k2": "v2, v3"})
        self.assertEqual(meta["name"], "a")

    def test_linea_indentada_sin_bloque_padre(self):
        with self.assertRaises(sk.SkillError):
            sk.parsear_frontmatter("---\nname: a\n  k1: v1\n---\ncuerpo")

    def test_errores(self):
        for texto in ("sin metadatos", "---\nname: a\nsin cierre", "---\nlinea sin dos puntos\n---\ncuerpo", ""):
            with self.subTest(texto=texto):
                with self.assertRaises(sk.SkillError):
                    sk.parsear_frontmatter(texto)


class TestValidacionDeSkills(unittest.TestCase):
    def _error(self, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            nombre = kw.pop("nombre", "mi-skill")
            d = crear_skill(tmp, nombre, **kw)
            with self.assertRaises(sk.SkillError) as ctx:
                sk.cargar_skill(d)
            return str(ctx.exception)

    def test_skill_valida_minima(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = sk.cargar_skill(crear_skill(tmp, "mi-skill"))
            self.assertEqual(s.nombre, "mi-skill")

    def test_sin_skill_md(self):
        self.assertIn("no tiene SKILL.md", self._error(md=False))

    def test_sin_skill_py(self):
        self.assertIn("falta skill.py", self._error(py=None))

    def test_name_ausente_o_invalido(self):
        base = "---\n{}description: " + DESC + "\nmetadata:\n  palabras_clave: x\n---\ncuerpo"
        self.assertIn("falta 'name'", self._error(md=base.format("")))
        self.assertIn("minúsculas", self._error(md=base.format("name: Mi_Skill\n")))

    def test_name_distinto_de_la_carpeta(self):
        md = f"---\nname: otra-cosa\ndescription: {DESC}\nmetadata:\n  palabras_clave: x\n---\ncuerpo"
        self.assertIn("coincidir con el nombre de la carpeta", self._error(md=md))

    def test_descripcion_corta_o_larga(self):
        for desc in ("corta", "x" * 1025):
            md = f"---\nname: mi-skill\ndescription: {desc}\nmetadata:\n  palabras_clave: x\n---\ncuerpo"
            self.assertIn("entre 20 y 1024", self._error(md=md))

    def test_los_campos_propios_van_dentro_de_metadata(self):
        """El estándar solo define name, description, license, compatibility, metadata y allowed-tools."""
        md = f"---\nname: mi-skill\ndescription: {DESC}\npalabras_clave: x\n---\ncuerpo"
        self.assertIn("no está definido por el estándar", self._error(md=md))
        md = f"---\nname: mi-skill\ndescription: {DESC}\nmetadata: texto suelto\n---\ncuerpo"
        self.assertIn("'metadata' debe ser un bloque", self._error(md=md))

    def test_campos_opcionales_del_estandar_se_aceptan(self):
        md = (f"---\nname: mi-skill\ndescription: {DESC}\nlicense: MIT\ncompatibility: Python 3.8+\n"
              "metadata:\n  palabras_clave: x\n---\ncuerpo")
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(sk.cargar_skill(crear_skill(tmp, "mi-skill", md=md)).nombre, "mi-skill")

    def test_compatibility_demasiado_larga(self):
        md = f"---\nname: mi-skill\ndescription: {DESC}\ncompatibility: {'x' * 501}\nmetadata:\n  palabras_clave: x\n---\ncuerpo"
        self.assertIn("500 caracteres", self._error(md=md))

    def test_nombres_que_el_estandar_prohibe(self):
        for nombre in ("-pdf", "pdf-", "pdf--processing", "PDF", "con_guion_bajo", "x" * 65):
            md = f"---\nname: {nombre}\ndescription: {DESC}\nmetadata:\n  palabras_clave: x\n---\ncuerpo"
            with self.subTest(nombre=nombre):
                with tempfile.TemporaryDirectory() as tmp:
                    d = crear_skill(tmp, "carpeta", md=md)
                    with self.assertRaises(sk.SkillError):
                        sk.cargar_skill(d)

    def test_sin_palabras_clave(self):
        md = f"---\nname: mi-skill\ndescription: {DESC}\n---\ncuerpo"
        self.assertIn("palabras_clave", self._error(md=md))

    def test_efecto_desconocido(self):
        md = f"---\nname: mi-skill\ndescription: {DESC}\nmetadata:\n  palabras_clave: x\n  efectos: borra_todo\n---\ncuerpo"
        self.assertIn("efecto desconocido", self._error(md=md))

    def test_cuerpo_vacio(self):
        md = f"---\nname: mi-skill\ndescription: {DESC}\nmetadata:\n  palabras_clave: x\n---\n"
        self.assertIn("cuerpo vacío", self._error(md=md))

    def test_skill_py_con_errores(self):
        self.assertIn("no se pudo cargar", self._error(py="esto no es python ("))
        self.assertIn("PARAMETROS", self._error(py="def ejecutar(sesion):\n    pass\n"))
        self.assertIn("ejecutar", self._error(py="PARAMETROS = {}\n"))
        self.assertIn("'tipo'", self._error(py="PARAMETROS = {'x': {'tipo': 'raro', 'descripcion': 'd'}}\ndef ejecutar(sesion, **a):\n    pass\n"))

    def test_efecto_de_escritura_exige_previsualizar(self):
        md = f"---\nname: mi-skill\ndescription: {DESC}\nmetadata:\n  palabras_clave: x\n  efectos: escribe_archivos\n---\ncuerpo"
        self.assertIn("previsualizar", self._error(md=md))

    def test_carpeta_de_skills_invalida(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(sk.SkillError):
                sk.cargar_skills(os.path.join(tmp, "no_existe"))
            with self.assertRaises(sk.SkillError):
                sk.cargar_skills(tmp)                          # carpeta vacía


class TestConfigAgentes(unittest.TestCase):
    def setUp(self):
        self.reg = sk.cargar_skills(SKILLS)

    def test_agentes_reales(self):
        cfgs = ca.cargar_agentes(os.path.join(helpers.RAIZ, "config", "agentes"), self.reg)
        self.assertEqual(sorted(cfgs), ["analista", "auditor"])
        self.assertEqual(cfgs["analista"].skills_permitidas, ["consulta-transacciones", "exportar-reporte"])
        self.assertEqual(cfgs["auditor"].skills_permitidas, ["diagnostico-invalidas", "exportar-reporte"])

    def test_el_comportamiento_de_cada_agente_es_distinto(self):
        cfgs = ca.cargar_agentes(os.path.join(helpers.RAIZ, "config", "agentes"), self.reg)
        self.assertFalse(cfgs["analista"].respuesta["mostrar_recomendacion"])
        self.assertTrue(cfgs["auditor"].respuesta["mostrar_recomendacion"])
        self.assertNotEqual(cfgs["analista"].tono, cfgs["auditor"].tono)

    def _agente_real(self):
        with open(os.path.join(helpers.RAIZ, "config", "agentes", "analista.json"), encoding="utf-8") as f:
            return json.load(f)

    def _error_agente(self, datos, nombre="analista"):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, f"{nombre}.json"), "w", encoding="utf-8") as f:
                json.dump(datos, f)
            with self.assertRaises(ca.ConfigError) as ctx:
                ca.cargar_agentes(tmp, self.reg)
            return str(ctx.exception)

    def test_agente_con_skill_inexistente(self):
        d = self._agente_real()
        d["skills_permitidas"] = ["no-existe"]
        self.assertIn("no existe en la carpeta de skills", self._error_agente(d))

    def test_agente_sin_skills(self):
        d = self._agente_real()
        d["skills_permitidas"] = []
        self.assertIn("no puede estar vacía", self._error_agente(d))

    def test_agente_con_campos_faltantes(self):
        for clave, pedazo in (("rol", "falta 'rol'"), ("respuesta", "falta 'respuesta'"), ("mensajes", "falta 'mensajes'")):
            d = self._agente_real()
            del d[clave]
            self.assertIn(pedazo, self._error_agente(d))
        d = self._agente_real()
        del d["mensajes"]["cancelado"]
        self.assertIn("mensajes.cancelado", self._error_agente(d))
        d = self._agente_real()
        del d["respuesta"]["prefijo"]
        self.assertIn("respuesta.prefijo", self._error_agente(d))

    def test_id_distinto_del_archivo(self):
        self.assertIn("coincidir con el nombre del archivo", self._error_agente(self._agente_real(), nombre="otro"))

    def test_json_malformado_y_carpeta_inexistente(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "x.json"), "w") as f:
                f.write("{ no es json")
            with self.assertRaises(ca.ConfigError):
                ca.cargar_agentes(tmp, self.reg)
            with self.assertRaises(ca.ConfigError):
                ca.cargar_agentes(os.path.join(tmp, "no_existe"), self.reg)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ca.ConfigError):
                ca.cargar_agentes(tmp, self.reg)               # sin ningún agente

    def test_sistema(self):
        s = ca.cargar_sistema(os.path.join(helpers.RAIZ, "config", "sistema.json"))
        self.assertEqual((s["confirmar_efectos"], s["max_filas"]), ("siempre", 10))
        origenes = {d["origen"] for d in s["decisiones"]}
        self.assertEqual(origenes, {"ESTUDIANTE", "PROPUESTA DE LA IA"})

    def test_sistema_invalido(self):
        casos = [{"confirmar_efectos": "a veces", "max_filas": 10}, {"confirmar_efectos": "siempre", "max_filas": 0},
                 {"confirmar_efectos": "siempre", "max_filas": True}, {"confirmar_efectos": "siempre"}, []]
        for datos in casos:
            with self.subTest(datos=datos):
                with tempfile.TemporaryDirectory() as tmp:
                    ruta = os.path.join(tmp, "sistema.json")
                    with open(ruta, "w") as f:
                        json.dump(datos, f)
                    with self.assertRaises(ca.ConfigError):
                        ca.cargar_sistema(ruta)


if __name__ == "__main__":
    unittest.main()
