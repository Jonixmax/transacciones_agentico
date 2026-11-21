"""
SKILLS: capacidades encapsuladas que el agente puede usar.

Una skill es una carpeta con:
    SKILL.md        metadatos (name, description, ...) + instrucciones en Markdown
    skill.py        código: PARAMETROS (esquema de argumentos) y ejecutar(sesion, **args)
    recursos/       archivos de apoyo (guías, vocabularios, plantillas)

DIVULGACIÓN PROGRESIVA: al arrancar solo se leen los metadatos (nombre y descripción), que
es lo único que el agente "ve" para decidir. Las instrucciones completas de SKILL.md se
cargan únicamente cuando una skill se elige (Skill.instrucciones), para no llenar el prompt.
"""
import importlib.util
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict

EFECTOS_VALIDOS = ("ninguno", "escribe_archivos")
TIPOS_PARAMETRO = ("texto", "entero", "texto_o_numero")
RE_NOMBRE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillError(Exception):
    """Una skill está mal definida (SKILL.md o skill.py incompletos o inválidos)."""


@dataclass
class ResultadoSkill:
    ok: bool
    texto: str
    recomendacion: str = ""
    datos: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Previsualizacion:
    """Lo que hará una skill con efectos, mostrado al usuario antes de pedir confirmación."""
    texto: str
    sobrescribe: bool = False


# Campos que define el estándar Agent Skills (agentskills.io). Cualquier campo propio va dentro de 'metadata'.
CAMPOS_ESTANDAR = ("name", "description", "license", "compatibility", "metadata", "allowed-tools")


def parsear_frontmatter(contenido):
    """Separa el bloque de metadatos '---' del cuerpo en Markdown. Devuelve (dict, cuerpo).

    Soporta 'clave: valor' y UN nivel de anidación (un bloque como 'metadata:' con líneas
    indentadas), que es lo que necesita el estándar. No es un parser YAML completo.
    """
    lineas = contenido.splitlines()
    if not lineas or lineas[0].strip() != "---":
        raise SkillError("SKILL.md debe empezar con un bloque de metadatos delimitado por '---'")
    meta, bloque, i = {}, None, 1
    while i < len(lineas) and lineas[i].strip() != "---":
        linea = lineas[i]
        if linea.strip():
            if ":" not in linea:
                raise SkillError(f"línea de metadatos inválida en SKILL.md: '{linea}'")
            clave, _, valor = linea.strip().partition(":")
            clave, valor = clave.strip(), valor.strip()
            if linea[0] in " \t":                              # línea indentada: pertenece al bloque anterior
                if bloque is None:
                    raise SkillError(f"línea indentada sin bloque padre en SKILL.md: '{linea.strip()}'")
                meta[bloque][clave] = valor
            elif valor == "":                                  # 'metadata:' abre un bloque anidado
                meta[clave], bloque = {}, clave
            else:
                meta[clave], bloque = valor, None
        i += 1
    if i >= len(lineas):
        raise SkillError("el bloque de metadatos de SKILL.md no se cierra con '---'")
    return meta, "\n".join(lineas[i + 1:]).strip()


class Skill:
    def __init__(self, nombre, descripcion, palabras_clave, efectos, directorio, parametros,
                 funcion_ejecutar, funcion_previsualizar=None):
        self.nombre = nombre
        self.descripcion = descripcion
        self.palabras_clave = palabras_clave
        self.efectos = efectos
        self.directorio = directorio
        self.parametros = parametros
        self._ejecutar = funcion_ejecutar
        self._previsualizar = funcion_previsualizar
        self._instrucciones = None

    @property
    def requiere_confirmacion(self):
        return "escribe_archivos" in self.efectos

    @property
    def instrucciones_cargadas(self):
        return self._instrucciones is not None

    def instrucciones(self):
        """Cuerpo de SKILL.md. Se lee del disco la primera vez que se pide (carga diferida)."""
        if self._instrucciones is None:
            with open(os.path.join(self.directorio, "SKILL.md"), encoding="utf-8") as f:
                self._instrucciones = parsear_frontmatter(f.read())[1]
        return self._instrucciones

    def recurso_json(self, nombre):
        with open(os.path.join(self.directorio, "recursos", nombre), encoding="utf-8") as f:
            return json.load(f)

    def vocabulario(self):
        """Sinónimos propios de la skill (solo los usa el modo simulado para interpretar texto)."""
        try:
            return self.recurso_json("vocabulario.json")
        except FileNotFoundError:
            return {}

    def ejecutar(self, sesion, **args):
        return self._ejecutar(sesion, **args)

    def previsualizar(self, sesion, **args):
        if self._previsualizar is None:
            return Previsualizacion(f"Voy a ejecutar la skill '{self.nombre}' con efectos.")
        return self._previsualizar(sesion, **args)

    def entrada_catalogo(self, permitida):
        """Lo que el modelo ve de la skill: nombre, descripción y esquema de argumentos."""
        return {"nombre": self.nombre, "descripcion": self.descripcion, "parametros": self.parametros,
                "palabras_clave": self.palabras_clave, "vocabulario": self.vocabulario(),
                "efectos": self.efectos, "permitida": permitida}


def cargar_skill(directorio):
    carpeta = os.path.basename(os.path.normpath(directorio))
    ruta_md = os.path.join(directorio, "SKILL.md")
    ruta_py = os.path.join(directorio, "skill.py")
    if not os.path.isfile(ruta_md):
        raise SkillError(f"la skill '{carpeta}' no tiene SKILL.md")
    with open(ruta_md, encoding="utf-8") as f:
        meta, cuerpo = parsear_frontmatter(f.read())

    for clave in meta:
        if clave not in CAMPOS_ESTANDAR:
            raise SkillError(f"'{carpeta}': el campo '{clave}' no está definido por el estándar de skills; "
                             f"los campos propios van dentro de 'metadata'")
    nombre, descripcion = meta.get("name", ""), meta.get("description", "")
    if not isinstance(nombre, str) or not isinstance(descripcion, str):
        raise SkillError(f"'{carpeta}': 'name' y 'description' deben ser texto en una sola línea")
    if not nombre:
        raise SkillError(f"'{carpeta}': falta 'name' en SKILL.md")
    if not RE_NOMBRE.match(nombre) or len(nombre) > 64:
        raise SkillError(f"'{carpeta}': 'name' debe ir en minúsculas con guiones (máx. 64): '{nombre}'")
    if nombre != carpeta:
        raise SkillError(f"'{carpeta}': 'name' ('{nombre}') debe coincidir con el nombre de la carpeta")
    if not (20 <= len(descripcion) <= 1024):
        raise SkillError(f"'{nombre}': 'description' debe tener entre 20 y 1024 caracteres")
    if len(str(meta.get("compatibility", ""))) > 500:
        raise SkillError(f"'{nombre}': 'compatibility' no puede superar 500 caracteres")
    propios = meta.get("metadata", {})
    if not isinstance(propios, dict):
        raise SkillError(f"'{nombre}': 'metadata' debe ser un bloque de pares clave: valor")
    palabras = [p.strip() for p in propios.get("palabras_clave", "").split(",") if p.strip()]
    if not palabras:
        raise SkillError(f"'{nombre}': falta 'metadata.palabras_clave' (las usa el modo simulado para elegir la skill)")
    efectos = [e.strip() for e in propios.get("efectos", "ninguno").split(",") if e.strip()]
    for e in efectos:
        if e not in EFECTOS_VALIDOS:
            raise SkillError(f"'{nombre}': efecto desconocido '{e}'. Usa {', '.join(EFECTOS_VALIDOS)}")
    if not cuerpo:
        raise SkillError(f"'{nombre}': SKILL.md no tiene instrucciones (cuerpo vacío)")
    if not os.path.isfile(ruta_py):
        raise SkillError(f"'{nombre}': falta skill.py")

    try:
        spec = importlib.util.spec_from_file_location(f"skill_{nombre.replace('-', '_')}", ruta_py)
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
    except Exception as e:
        raise SkillError(f"'{nombre}': skill.py no se pudo cargar ({e!r})")
    parametros = getattr(modulo, "PARAMETROS", None)
    if not isinstance(parametros, dict):
        raise SkillError(f"'{nombre}': skill.py debe definir PARAMETROS (dict)")
    for p, spec_p in parametros.items():
        if not isinstance(spec_p, dict) or spec_p.get("tipo") not in TIPOS_PARAMETRO or not spec_p.get("descripcion"):
            raise SkillError(f"'{nombre}': el parámetro '{p}' necesita 'tipo' ({', '.join(TIPOS_PARAMETRO)}) y 'descripcion'")
    if not callable(getattr(modulo, "ejecutar", None)):
        raise SkillError(f"'{nombre}': skill.py debe definir la función ejecutar(sesion, **args)")
    previsualizar = getattr(modulo, "previsualizar", None)
    if "escribe_archivos" in efectos and not callable(previsualizar):
        raise SkillError(f"'{nombre}': una skill que escribe archivos debe definir previsualizar(sesion, **args)")
    return Skill(nombre, descripcion, palabras, efectos, directorio, parametros, modulo.ejecutar, previsualizar)


class RegistroSkills:
    def __init__(self, skills):
        self._skills = {s.nombre: s for s in skills}

    def __contains__(self, nombre):
        return nombre in self._skills

    def get(self, nombre):
        return self._skills.get(nombre)

    def todas(self):
        return list(self._skills.values())

    def nombres(self):
        return list(self._skills)

    def catalogo(self, permitidas):
        return [s.entrada_catalogo(s.nombre in permitidas) for s in self._skills.values()]


def cargar_skills(raiz):
    if not os.path.isdir(raiz):
        raise SkillError(f"no existe la carpeta de skills '{raiz}'")
    carpetas = sorted(d for d in os.listdir(raiz)
                      if os.path.isdir(os.path.join(raiz, d)) and not d.startswith((".", "_")))
    skills = [cargar_skill(os.path.join(raiz, d)) for d in carpetas]
    if not skills:
        raise SkillError(f"la carpeta '{raiz}' no contiene ninguna skill")
    return RegistroSkills(skills)
