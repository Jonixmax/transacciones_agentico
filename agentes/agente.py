"""
AGENTE: bucle  mensaje -> decidir (LLM) -> validar (guardas) -> [confirmar] -> skill -> redactar.

Lo que hace al agente "personalizado" NO está aquí sino en su configuración (config/agentes/*.json):
rol, objetivo, tono, reglas de comportamiento, skills permitidas y mensajes. Este código es el
mismo para todos los agentes.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from .guardas import AccionInvalida, validar_accion


@dataclass
class Respuesta:
    texto: str
    estado: str                     # ok | necesita_confirmacion | error | fuera_de_alcance | aclarar | ...
    skill: Optional[str] = None
    trazas: List[str] = field(default_factory=list)


class _Seguro(dict):
    """Para str.format_map: un campo desconocido se deja tal cual en lugar de fallar."""
    def __missing__(self, clave):
        return "{" + clave + "}"


class Agente:
    def __init__(self, config, registro, cliente, sesion, politica_efectos, todos_los_agentes=None):
        self.config = config
        self.registro = registro
        self.cliente = cliente
        self.sesion = sesion
        self.politica_efectos = politica_efectos          # siempre | nunca | solo_sobrescribir
        self.todos = todos_los_agentes or {config.id: config}
        self.historial = []
        self.ultima_traza = []
        self._pendiente = None                            # (skill, args) esperando confirmación
        self._trazas_previas = []                         # pasos que llevaron a pedir la confirmación

    # ---------------------------------------------------------------- prompt estructurado
    def prompt_sistema(self):
        """El prompt que recibiría un LLM real: secciones fijas + skills (solo nombre y descripción)."""
        c = self.config
        reglas = "\n".join(f"- {r}" for r in c.reglas_comportamiento)
        skills = "\n".join(f"- {n}: {self.registro.get(n).descripcion}" for n in c.skills_permitidas)
        return (
            f"# ROL\nEres {c.nombre}, {c.rol}.\n\n"
            f"# OBJETIVO\n{c.objetivo}\n\n"
            f"# TONO\n{c.tono}\n\n"
            f"# REGLAS DE COMPORTAMIENTO\n{reglas}\n\n"
            f"# SKILLS DISPONIBLES\n{skills}\n\n"
            f"# POLÍTICA DE EFECTOS\nConfirmación antes de escribir archivos: {self.politica_efectos}.\n\n"
            "# FORMATO DE RESPUESTA\nResponde SOLO con un JSON: "
            '{"accion": "skill", "skill": "<nombre>", "args": {...}} o {"accion": "no_entendido"}.'
        )

    def _msg(self, clave, **extra):
        c = self.config
        objetivo_inf = c.objetivo.rstrip(". ")
        objetivo_inf = objetivo_inf[:1].lower() + objetivo_inf[1:]      # "Responder..." -> "responder..."
        datos = _Seguro(nombre=c.nombre, rol=c.rol, objetivo=c.objetivo, objetivo_inf=objetivo_inf, **extra)
        return c.mensajes[clave].format_map(datos)

    def texto_saludo(self):
        return self._msg("saludo")

    def _comportamiento(self):
        return {**self.config.respuesta, "nombre": self.config.nombre}

    def _agentes_con(self, skill):
        return [a.id for a in self.todos.values() if skill in a.skills_permitidas]

    def texto_ayuda(self):
        lineas = [f"Soy {self.config.nombre} ({self.config.rol}). Puedo ayudarte con:"]
        for n in self.config.skills_permitidas:
            s = self.registro.get(n)
            marca = "  [pide confirmación: escribe archivos]" if s.requiere_confirmacion else ""
            lineas.append(f"  - {n}: {s.descripcion}{marca}")
        lineas.append("Escribe tu consulta en lenguaje natural. Comandos: /agente, /skills, /prompt, /traza, /cargar, /salir")
        return "\n".join(lineas)

    # ---------------------------------------------------------------- bucle principal
    def atender(self, texto):
        self._pendiente = None                            # un mensaje nuevo cancela una confirmación abierta
        trazas = []
        texto = (texto or "").strip()
        if not texto:
            return self._cerrar(Respuesta(self._msg("no_entendido"), "no_entendido"), trazas)
        self.historial.append({"rol": "usuario", "texto": texto})

        catalogo = self.registro.catalogo(set(self.config.skills_permitidas))
        try:
            accion = self.cliente.decidir(self.prompt_sistema(), self.historial, catalogo)
            accion = validar_accion(accion, self.registro, set(self.config.skills_permitidas))
        except AccionInvalida as e:
            trazas.append(f"guarda: acción rechazada ({e})")
            return self._cerrar(Respuesta(f"No ejecuté nada: {e}.", "error"), trazas)
        except Exception as e:                            # el modelo falló: el agente no se cae
            trazas.append(f"modelo: error ({e!r})")
            return self._cerrar(Respuesta(f"El modelo no pudo responder ({e}).", "error"), trazas)
        trazas.append(f"decisión: {accion}")

        tipo = accion["accion"]
        if tipo == "saludo":
            return self._cerrar(Respuesta(self._msg("saludo"), "ok"), trazas)
        if tipo == "ayuda":
            return self._cerrar(Respuesta(self.texto_ayuda(), "ok"), trazas)
        if tipo == "no_entendido":
            return self._cerrar(Respuesta(self._msg("no_entendido"), "no_entendido"), trazas)
        if tipo == "aclarar":
            return self._cerrar(Respuesta(self._msg("aclarar", opciones=", ".join(accion["opciones"])), "aclarar"), trazas)
        if tipo == "fuera_de_alcance":
            duenos = self._agentes_con(accion["skill"])
            texto_derivar = " o ".join(f"/agente {d}" for d in duenos) or "otro agente"
            return self._cerrar(Respuesta(self._msg("fuera_de_alcance", skill=accion["skill"], derivar=texto_derivar),
                                          "fuera_de_alcance", skill=accion["skill"]), trazas)
        return self._ejecutar_skill(self.registro.get(accion["skill"]), accion.get("args", {}), trazas)

    def _ejecutar_skill(self, skill, args, trazas):
        if not self.sesion.tiene_datos:
            return self._cerrar(Respuesta(self._msg("sin_datos"), "sin_datos"), trazas)
        if skill.requiere_confirmacion:
            try:
                previa = skill.previsualizar(self.sesion, **args)
            except (ValueError, TypeError) as e:
                trazas.append(f"previsualización rechazada: {e}")
                return self._cerrar(Respuesta(f"No ejecuté nada: {e}", "error", skill.nombre), trazas)
            exige = self.politica_efectos == "siempre" or (self.politica_efectos == "solo_sobrescribir" and previa.sobrescribe)
            if exige:
                self._pendiente = (skill, args)
                self._trazas_previas = list(trazas)
                trazas.append(f"política: '{skill.nombre}' tiene efectos -> se pide confirmación")
                return self._cerrar(Respuesta(f"{previa.texto}\n¿Confirmas? (s/n)", "necesita_confirmacion", skill.nombre), trazas)
        return self._correr(skill, args, trazas)

    def _correr(self, skill, args, trazas):
        instrucciones = skill.instrucciones()             # carga diferida: recién ahora se lee SKILL.md
        trazas.append(f"skill: {skill.nombre} {args} (instrucciones cargadas: {len(instrucciones)} caracteres)")
        try:
            resultado = skill.ejecutar(self.sesion, **args)
        except Exception as e:
            trazas.append(f"skill: error ({e!r})")
            return self._cerrar(Respuesta(f"La skill '{skill.nombre}' falló: {e}", "error", skill.nombre), trazas)
        trazas.append(f"observación: {resultado.texto.splitlines()[0][:90] if resultado.texto else ''}")
        self.historial.append({"rol": "skill", "texto": instrucciones})
        texto = self.cliente.redactar(self.prompt_sistema(), self.historial, resultado, self._comportamiento())
        estado = "ok" if resultado.ok else "error"
        return self._cerrar(Respuesta(texto, estado, skill.nombre), trazas)

    def confirmar(self, acepta):
        """Resuelve una acción pendiente. Solo aquí se ejecutan las skills con efectos."""
        if self._pendiente is None:
            return self._cerrar(Respuesta("No hay ninguna acción pendiente de confirmar.", "ok"), [])
        trazas = list(self._trazas_previas) + ["política: la skill con efectos se pidió confirmar al usuario"]
        skill, args = self._pendiente
        self._pendiente = None
        if not acepta:
            trazas.append(f"confirmación: el usuario canceló '{skill.nombre}'")
            return self._cerrar(Respuesta(self._msg("cancelado"), "cancelado", skill.nombre), trazas)
        trazas.append(f"confirmación: el usuario aceptó '{skill.nombre}'")
        return self._correr(skill, args, trazas)

    @property
    def pendiente(self):
        return self._pendiente is not None

    def _cerrar(self, respuesta, trazas):
        respuesta.trazas = trazas
        self.ultima_traza = trazas
        self.historial.append({"rol": "agente", "texto": respuesta.texto})
        return respuesta
