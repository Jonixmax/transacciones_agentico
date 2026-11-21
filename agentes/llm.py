"""
CLIENTE LLM: la interfaz que el agente usa para "pensar", y su implementación simulada.

ClienteLLM define el contrato. Un cliente REAL (OpenAI, Anthropic, Gemini...) implementaría
decidir() enviando el prompt y el catálogo al modelo y devolviendo su acción en JSON, y
redactar() pidiéndole la respuesta final. El agente no cambia: solo se cambia el cliente.

ModoSimulado NO es un LLM. Es un planificador determinista, sin conexión ni API key, que imita
dos cosas: (1) elegir la skill leyendo su descripción y palabras clave, y extraer los
argumentos del texto; (2) redactar la respuesta con la configuración del agente. Sirve para
demostrar y probar la arquitectura de forma reproducible.
"""
import re
import unicodedata
import json
import os
import urllib.error
import urllib.parse
import urllib.request

STOPWORDS = {
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "al", "a", "en", "y", "o", "u",
    "que", "por", "con", "para", "se", "es", "me", "mi", "lo", "su", "sus", "este", "esta", "esto",
    "hay", "son", "tiene", "tienen", "cual", "cuales", "como", "mas", "menos", "todo", "todas", "todos",
}
SALUDOS = {"hola", "buenas", "buenos", "hey", "saludos"}


def normalizar(texto):
    """Minúsculas y sin acentos (conserva $, € y £)."""
    sin_acentos = "".join(c for c in unicodedata.normalize("NFD", str(texto)) if unicodedata.category(c) != "Mn")
    return sin_acentos.lower()


def tokens(texto):
    return re.findall(r"[a-z0-9$€£]+", normalizar(texto))


def raices(texto):
    """Raíz = primeros 4 caracteres: 'transacciones' y 'transaccion' coinciden."""
    return {t[:4] for t in tokens(texto) if t not in STOPWORDS}


class ClienteLLM:
    """Contrato que debe cumplir cualquier cliente (simulado o real)."""

    def decidir(self, prompt_sistema, historial, catalogo):
        """Devuelve una acción: {"accion": "skill", "skill": nombre, "args": {...}} u otro tipo."""
        raise NotImplementedError

    def redactar(self, prompt_sistema, historial, resultado, comportamiento):
        """Devuelve el texto final para el usuario a partir del resultado de la skill."""
        raise NotImplementedError


# ----------------------------------------------------------------------
# Extracción de argumentos (heurística del modo simulado)
# ----------------------------------------------------------------------
_NUM = r"(\d+(?:[.,]\d+)?)(?![\d/\-])"          # número que NO es parte de una fecha
_MON = r"\s*[$€£]?\s*"
RE_MIN = re.compile(r"(?<!no )(?:mayor(?:es)?|superior(?:es)?|mas)\s+(?:o\s+igual\s+)?(?:a|que|de)" + _MON + _NUM)
RE_MIN2 = re.compile(r"(?:al\s+menos|minimo(?:\s+de)?|desde)" + _MON + _NUM)
RE_MAX = re.compile(r"(?:menor(?:es)?|inferior(?:es)?|menos)\s+(?:o\s+igual\s+)?(?:a|que|de)" + _MON + _NUM)
RE_MAX2 = re.compile(r"(?:hasta|maximo(?:\s+de)?|como\s+maximo|no\s+mas\s+de)" + _MON + _NUM)
RE_FUENTE = re.compile(r"fuente[ _-]*([a-z])(?![a-z0-9])")
RE_POSICION = re.compile(r"(?:registro|numero|posicion|linea|fila)\s*#?\s*(\d+)|#\s*(\d+)")
RE_CARPETA = re.compile(r"(?:carpeta|directorio)\s+(?:llamada\s+|de\s+nombre\s+)?['\"]?([a-z0-9_\-./]+)")


def _contiene(lista_tokens, sinonimo):
    partes = sinonimo.split()
    n = len(partes)
    return any(lista_tokens[i:i + n] == partes for i in range(len(lista_tokens) - n + 1))


def _buscar_en_vocabulario(grupo, lista_tokens):
    """Primera clave del grupo (en orden) con algún sinónimo presente en el texto."""
    for clave, sinonimos in grupo.items():
        if any(_contiene(lista_tokens, s) for s in sinonimos):
            return clave
    return None


def _fechas(nt):
    encontradas = []
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", nt):
        encontradas.append((m.start(), m.group(0)))
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", nt):
        encontradas.append((m.start(), f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"))
    encontradas.sort()
    if not encontradas:
        return {}
    if re.search(r"\bentre\b", nt) and len(encontradas) >= 2:
        return {"fecha_desde": encontradas[0][1], "fecha_hasta": encontradas[1][1]}
    res = {}
    for pos, iso in encontradas:
        previo = nt[max(0, pos - 16):pos]
        if re.search(r"(desde|partir de|despues de)\s*(el\s*)?$", previo):
            res["fecha_desde"] = iso
        elif re.search(r"(hasta|antes de)\s*(el\s*)?$", previo):
            res["fecha_hasta"] = iso
        else:                                            # una fecha suelta = ese día completo
            res["fecha_desde"] = res["fecha_hasta"] = iso
    return res


def extraer_argumentos(parametros, texto, vocabulario):
    """Interpreta el texto del usuario según los parámetros que declara la skill."""
    nt = normalizar(texto)
    toks = tokens(texto)
    args = {}

    if "operacion" in parametros:
        op = _buscar_en_vocabulario(vocabulario.get("operaciones", {}), toks)
        if op:
            args["operacion"] = op
    if "estado" in parametros:
        e = _buscar_en_vocabulario(vocabulario.get("estados", {}), toks)
        if e:
            args["estado"] = e
    if "moneda" in parametros:
        m = _buscar_en_vocabulario(vocabulario.get("monedas", {}), toks)
        if m:
            args["moneda"] = m
    if "fuente" in parametros:
        m = RE_FUENTE.search(nt)
        if m:
            args["fuente"] = f"fuente_{m.group(1)}"
    if "monto_min" in parametros or "monto_max" in parametros:
        maximo = RE_MAX.search(nt) or RE_MAX2.search(nt)
        minimo = RE_MIN.search(nt) or RE_MIN2.search(nt)
        if maximo and "monto_max" in parametros:
            args["monto_max"] = maximo.group(1)
        if minimo and "monto_min" in parametros:
            args["monto_min"] = minimo.group(1)
    if "fecha_desde" in parametros:
        args.update(_fechas(nt))
    if "id" in parametros and (args.get("operacion") == "buscar" or "id" in toks):
        m = (re.search(r"\bid\s*[:=]?\s*([a-z0-9_\-]+)", nt)
             or re.search(r"transaccion(?:es)?\s+(?:numero\s+)?([a-z0-9_\-]*\d[a-z0-9_\-]*)", nt)
             or re.search(r"\b([a-z]+[-_]\d+)\b", nt))
        if m:
            args["id"] = m.group(1)
    if "posicion" in parametros:
        m = RE_POSICION.search(nt)
        if m:
            args["posicion"] = int(m.group(1) or m.group(2))
    if "motivo" in parametros:
        k = _buscar_en_vocabulario(vocabulario.get("motivos", {}), toks)
        if k:
            args["motivo"] = k
    if "carpeta" in parametros:
        m = RE_CARPETA.search(nt)
        if m:
            args["carpeta"] = m.group(1)
    return args


# ----------------------------------------------------------------------
# Cliente simulado
# ----------------------------------------------------------------------
class ModoSimulado(ClienteLLM):
    def decidir(self, prompt_sistema, historial, catalogo):
        texto = next((m["texto"] for m in reversed(historial) if m["rol"] == "usuario"), "")
        toks = set(tokens(texto))
        if not toks:
            return {"accion": "no_entendido"}
        if toks & SALUDOS and len(toks) <= 3:
            return {"accion": "saludo"}
        if toks & {"ayuda", "help"} or ("puedes" in toks and toks & {"hacer", "ayudar"}):
            return {"accion": "ayuda"}

        raices_texto = raices(texto)
        puntajes = []
        for entrada in catalogo:
            clave = set()
            for k in entrada["palabras_clave"]:
                clave |= raices(k)
            aciertos = len(raices_texto & clave)
            if aciertos:                                     # sin ninguna palabra clave no es candidata
                puntajes.append((aciertos * 2 + len(raices_texto & raices(entrada["descripcion"])), entrada))
        if not puntajes:
            return {"accion": "no_entendido"}

        mejor = max(p for p, _ in puntajes)
        permitidas = [(p, e) for p, e in puntajes if e["permitida"]]
        mejor_permitida = max((p for p, _ in permitidas), default=-1)
        if mejor > mejor_permitida:
            ajena = next(e for p, e in puntajes if p == mejor and not e["permitida"])
            return {"accion": "fuera_de_alcance", "skill": ajena["nombre"]}
        candidatas = [e for p, e in permitidas if p == mejor_permitida]
        if len(candidatas) > 1:
            return {"accion": "aclarar", "opciones": [e["nombre"] for e in candidatas]}
        elegida = candidatas[0]
        return {"accion": "skill", "skill": elegida["nombre"],
                "args": extraer_argumentos(elegida["parametros"], texto, elegida["vocabulario"]),
                "razon": f"el mensaje coincide con la descripción de '{elegida['nombre']}'"}

    def redactar(self, prompt_sistema, historial, resultado, comportamiento):
        partes = []
        if comportamiento.get("prefijo"):
            partes.append(comportamiento["prefijo"])
        partes.append(resultado.texto)
        if comportamiento.get("mostrar_recomendacion") and resultado.recomendacion:
            partes.append(f"{comportamiento.get('etiqueta_recomendacion', 'Recomendación')}: {resultado.recomendacion}")
        if comportamiento.get("cierre"):
            partes.append(comportamiento["cierre"])
        return "\n".join(partes)


class ClienteGemini(ClienteLLM):
    """Cliente real de Google Gemini mediante la API REST oficial."""

    def __init__(self, api_key=None, model=None, timeout=30):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError("Falta GEMINI_API_KEY. Configura tu clave de API de Google Gemini.")

    def _solicitar(self, prompt_sistema, mensajes, forzar_json=False):
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={urllib.parse.quote(self.api_key, safe='')}"
        )
        contents = []
        for mensaje in mensajes[-20:]:
            rol = "model" if mensaje["rol"] in ("agente", "skill") else "user"
            contents.append({
                "role": rol,
                "parts": [{"text": mensaje["texto"]}],
            })
        cuerpo = {
            "system_instruction": {
                "parts": [{"text": prompt_sistema}],
            },
            "contents": contents,
        }
        if forzar_json:
            cuerpo["generationConfig"] = {
                "temperature": 0,
                "responseMimeType": "application/json",
            }

        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8")
        solicitud = urllib.request.Request(
            url,
            data=datos,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(solicitud, timeout=self.timeout) as respuesta:
                payload = json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detalle = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Gemini respondió HTTP {e.code}: {detalle}") from e
        except urllib.error.URLError as e:
            raise RuntimeError(f"No se pudo conectar con Gemini: {e.reason}") from e

        try:
            return payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError("Gemini devolvió una respuesta sin texto utilizable") from e

    def _json(self, texto):
        texto = texto.strip()
        if texto.startswith("```"):
            texto = re.sub(r"^```(?:json)?\s*", "", texto, flags=re.I)
            texto = re.sub(r"\s*```$", "", texto)
        inicio = texto.find("{")
        fin = texto.rfind("}")
        if inicio >= 0 and fin >= inicio:
            texto = texto[inicio:fin + 1]
        try:
            accion = json.loads(texto)
        except json.JSONDecodeError as e:
            raise ValueError(f"Gemini no devolvió JSON válido: {texto}") from e
        if not isinstance(accion, dict):
            raise ValueError("Gemini no devolvió un objeto JSON")
        return accion

    def decidir(self, prompt_sistema, historial, catalogo):
        catalogo_json = json.dumps(catalogo, ensure_ascii=False)
        mensaje = (
            "CATÁLOGO DE SKILLS PERMITIDAS:\n"
            f"{catalogo_json}\n\n"
            "Devuelve únicamente la acción JSON solicitada por el prompt del sistema."
        )
        contexto = list(historial[-20:])
        contexto.append({"rol": "usuario", "texto": mensaje})
        texto = self._solicitar(prompt_sistema, contexto, forzar_json=True)
        return self._json(texto)

    def redactar(self, prompt_sistema, historial, resultado, comportamiento):
        datos = {
            "resultado": resultado.texto,
            "recomendacion": resultado.recomendacion,
            "comportamiento": comportamiento,
        }
        mensaje = (
            "Redacta la respuesta final para el usuario usando este resultado y comportamiento.\n"
            "Responde con texto normal, no con JSON, aunque el prompt del sistema anterior describa "
            "el formato JSON usado para decidir acciones.\n"
            f"{json.dumps(datos, ensure_ascii=False)}"
        )
        return self._solicitar(
            prompt_sistema,
            list(historial[-20:]) + [{"rol": "usuario", "texto": mensaje}],
        ).strip()
