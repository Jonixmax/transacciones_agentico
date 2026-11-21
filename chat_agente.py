"""
CHAT: interfaz de conversación con los agentes.

Solo se encarga de leer lo que escribe el usuario y mostrar lo que responde el agente. La
entrada y la salida se pueden reemplazar (entrada/salida) para probarla sin teclado.
"""
import glob
import os

from nucleo.procesador import DatosError

CARPETA_DATOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "datos")
AYUDA_COMANDOS = (
    "Comandos:\n"
    "  /agente [nombre]   cambiar de agente (sin nombre: lista los agentes)\n"
    "  /skills            ver las skills y qué agente las usa\n"
    "  /prompt            ver el prompt estructurado del agente actual\n"
    "  /traza             ver los pasos de la última respuesta\n"
    "  /cargar [archivo]  cargar otro archivo de datos\n"
    "  /ayuda             mostrar esta ayuda\n"
    "  /salir             terminar\n"
    "Cualquier otro texto se envía al agente actual."
)


class SalirChat(Exception):
    pass


class Chat:
    def __init__(self, ecosistema, agente_inicial="analista", entrada=input, salida=print):
        self.eco = ecosistema
        self.entrada = entrada
        self.salida = salida
        if agente_inicial not in ecosistema.agentes:
            raise ValueError(f"agente desconocido: '{agente_inicial}'")
        self.actual = agente_inicial

    # ------------------------------------------------------------------ utilidades
    @property
    def agente(self):
        return self.eco.agentes[self.actual]

    def _pedir(self, mensaje):
        try:
            return self.entrada(mensaje).strip()
        except (EOFError, KeyboardInterrupt):
            raise SalirChat()

    def _decir(self, texto=""):
        self.salida(texto)

    def _confirmar(self, mensaje):
        while True:
            r = self._pedir(mensaje).lower()
            if r in ("s", "si", "sí", "y", "yes"):
                return True
            if r in ("n", "no"):
                return False
            self._decir("Responde 's' o 'n'.")

    # ------------------------------------------------------------------ carga de datos
    def elegir_archivo(self):
        archivos = sorted(glob.glob(os.path.join(CARPETA_DATOS, "*.json")))
        self._decir("\nArchivos de ejemplo en datos/:")
        for i, ruta in enumerate(archivos, start=1):
            self._decir(f"  {i}. {os.path.basename(ruta)}")
        self._decir("  (o escribe la ruta de otro archivo JSON; Enter vacío para salir)")
        while True:
            texto = self._pedir("Número o ruta: ")
            if not texto:
                return None
            if texto.isdigit() and 1 <= int(texto) <= len(archivos):
                return archivos[int(texto) - 1]
            if texto.isdigit():
                self._decir("Número fuera de rango.")
                continue
            return texto.strip('"')

    def cargar(self, ruta):
        sesion = self.eco.sesion
        previa = (sesion.resultado, sesion.ruta)
        try:
            sesion.cargar_archivo(ruta)
        except DatosError as e:
            sesion.resultado, sesion.ruta = previa
            self._decir(f"Error: {e}")
            return False
        r = sesion.resultado
        self._decir(f"Archivo cargado: {r.total} registros ({len(r.valid)} válidos, {len(r.invalid)} inválidos).")
        return True

    def _comando_cargar(self, argumento):
        sesion = self.eco.sesion
        ruta = argumento or self.elegir_archivo()
        if not ruta:
            return
        politica = self.eco.sistema["confirmar_efectos"]
        if sesion.tiene_datos and politica != "nunca":          # decisión del estudiante: confirmar siempre
            if not self._confirmar(f"Ya hay datos cargados ('{os.path.basename(sesion.ruta)}'). "
                                   f"¿Reemplazarlos con '{ruta}'? (s/n): "):
                self._decir("Carga cancelada. Se conservan los datos actuales.")
                return
        self.cargar(ruta)

    # ------------------------------------------------------------------ comandos
    def _cmd_agente(self, nombre):
        agentes = self.eco.agentes
        if not nombre:
            for i, a in agentes.items():
                marca = "  <- actual" if i == self.actual else ""
                self._decir(f"  {i}: {a.config.rol}{marca}")
            return
        if nombre not in agentes:
            self._decir(f"No existe el agente '{nombre}'. Disponibles: {', '.join(agentes)}.")
            return
        self.actual = nombre
        self._decir(f"Ahora hablas con {self.agente.config.nombre}.")

    def _cmd_skills(self):
        for s in self.eco.registro.todas():
            usan = [i for i, c in self.eco.configs.items() if s.nombre in c.skills_permitidas]
            efecto = "escribe archivos" if s.requiere_confirmacion else "solo lectura"
            self._decir(f"  {s.nombre}  [{efecto}]  agentes: {', '.join(usan) or 'ninguno'}")
            self._decir(f"      {s.descripcion}")

    def _comando(self, texto):
        partes = texto.split(maxsplit=1)
        cmd, arg = partes[0].lower(), (partes[1].strip() if len(partes) > 1 else "")
        if cmd == "/salir":
            raise SalirChat()
        if cmd == "/ayuda":
            self._decir(AYUDA_COMANDOS)
        elif cmd == "/agente":
            self._cmd_agente(arg.lower())
        elif cmd == "/skills":
            self._cmd_skills()
        elif cmd == "/prompt":
            self._decir(self.agente.prompt_sistema())
        elif cmd == "/traza":
            for paso in self.agente.ultima_traza or ["(todavía no hay trazas)"]:
                self._decir(f"  - {paso}")
        elif cmd == "/cargar":
            self._comando_cargar(arg)
        else:
            self._decir(f"Comando desconocido: {cmd}. Escribe /ayuda.")

    # ------------------------------------------------------------------ bucle
    def ejecutar(self, ruta=None):
        try:
            if ruta:
                self.cargar(ruta)
            while not self.eco.sesion.tiene_datos:
                ruta = self.elegir_archivo()
                if ruta is None:
                    self._decir("Hasta luego.")
                    return
                self.cargar(ruta)
            self._decir("\n" + self.agente.texto_saludo())
            self._decir("(Escribe /ayuda para ver los comandos)")
            while True:
                texto = self._pedir(f"\n[{self.agente.config.nombre}] > ")
                if not texto:
                    continue
                if texto.startswith("/"):
                    self._comando(texto)
                    continue
                respuesta = self.agente.atender(texto)
                self._decir(respuesta.texto)
                if respuesta.estado == "necesita_confirmacion":
                    final = self.agente.confirmar(self._confirmar("> "))
                    self._decir(final.texto)
        except SalirChat:
            self._decir("\nHasta luego.")
