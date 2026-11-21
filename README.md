# 🤖 Sistema de Transacciones con Agentes Personalizados y Skills Propias

Refactorización del sistema de normalización de transacciones multifuente (actividad anterior) para convertirlo en un **sistema agéntico modular**: el motor de datos queda separado, sus capacidades se encapsulan en **skills** (`SKILL.md` + código + recursos) y dos **agentes personalizados** por configuración las usan.

> **Actividad:** Refactorización y Personalización de un Sistema Agéntico mediante Skills Propias
> **Curso:** AI for Developers Jr. 4 · KODIGO Academy
> **Autor:** Jonathan Alberto
> **IA de apoyo:** Claude (Anthropic)

La nota técnica con las decisiones de diseño está en [`NOTA_TECNICA.md`](NOTA_TECNICA.md).

> ⚠️ **Aclaración honesta sobre el modelo.** El sistema funciona sin conexión con `--llm simulado`, un planificador determinista que no es un LLM real. También incluye un cliente para Google Gemini, que requiere una API key y conexión a internet (ver [Conectar un LLM real](#-conectar-un-llm-real)).

---

## 📋 Contenido

1. [Ejecución](#-ejecución)
2. [Arquitectura](#-arquitectura)
3. [Estructura del proyecto](#-estructura-del-proyecto)
4. [Refactorización realizada](#-refactorización-realizada)
5. [Skills](#-skills)
6. [Agentes y personalización](#-agentes-y-personalización)
7. [Seguridad: guardas y confirmación](#-seguridad-guardas-y-confirmación)
8. [Conectar un LLM real](#-conectar-un-llm-real)
9. [Decisiones: mías y propuestas de la IA](#-decisiones-mías-y-propuestas-de-la-ia)
10. [Ejemplo de conversación](#-ejemplo-de-conversación)
11. [Pruebas](#-pruebas)
12. [Uso de la IA y ajustes sobre sus sugerencias](#-uso-de-la-ia-y-ajustes-sobre-sus-sugerencias)
13. [Limitaciones conocidas](#-limitaciones-conocidas)

---

## 🚀 Ejecución

**Requisitos:** Python 3.8 o superior (desarrollado y probado con Python 3.12). Solo usa la librería estándar.

```bash
python main.py                                         # chat con el agente Analista
python main.py datos/transacciones_validas.json        # indicando el archivo
python main.py --agente auditor datos/transacciones_con_errores.json
python main.py clasico                                 # CLI clásica con menú (sin agentes)

python -m unittest discover -s tests -v                # las 190 pruebas automatizadas
```

**Comandos del chat:** `/agente [nombre]`, `/skills`, `/prompt` (ver el prompt estructurado), `/traza` (ver los pasos de la última respuesta), `/cargar [archivo]`, `/ayuda`, `/salir`. Cualquier otro texto se envía al agente en lenguaje natural.

---

## 🏗️ Arquitectura

```
                    ┌────────────────────────── chat_agente.py (interfaz) ─────────────────────────┐
                    │                                                                                │
   mensaje ──────►  │  AGENTE (config/agentes/*.json: rol, tono, reglas, skills permitidas)         │
                    │    1. construye el prompt estructurado (solo nombre + descripción de skills)  │
                    │    2. ClienteLLM.decidir()  ─►  acción propuesta                              │
                    │    3. GUARDAS validan la acción (skill existe, permitida, args y tipos)       │
                    │    4. si la skill tiene efectos ─► previsualiza y PIDE CONFIRMACIÓN           │
                    │    5. carga las instrucciones de SKILL.md (recién ahora) y ejecuta la skill   │
                    │    6. ClienteLLM.redactar()  ─►  respuesta con el estilo del agente           │
                    └───────────────────────────────┬────────────────────────────────────────────────┘
                                                    │ usa
                       skills/  (consulta-transacciones · diagnostico-invalidas · exportar-reporte)
                                                    │ usan
                       nucleo/  (reglas · normalización · validación · métricas · filtros · exportación)
```

Cada capa solo conoce a la de abajo: el motor (`nucleo/`) no sabe que existen agentes, y las skills no saben qué agente las usa.

---

## 📁 Estructura del proyecto

```
transacciones_agentico/
├── main.py                    # Punto de entrada (chat | clasico)
├── chat_agente.py             # Interfaz de conversación
├── interfaz_clasica.py        # CLI con menú de la actividad anterior (refactorizada)
├── nucleo/                    # MOTOR de datos (sin nada de agentes)
│   ├── reglas.json            #   reglas de normalización y validación
│   ├── config.py · modelos.py · normalizador.py · validador.py · procesador.py
│   ├── metricas.py · filtros.py
│   └── exportacion.py · presentacion.py     # extraídos de la interfaz en esta refactorización
├── agentes/                   # RUNTIME agéntico
│   ├── skills.py              #   carga y valida skills (divulgación progresiva)
│   ├── guardas.py             #   valida las acciones del modelo antes de ejecutarlas
│   ├── llm.py                 #   interfaz ClienteLLM + ModoSimulado
│   ├── agente.py              #   bucle del agente
│   ├── config_agentes.py · sesion.py · fabrica.py
├── skills/                    # CAPACIDADES (cada una: SKILL.md + skill.py + recursos/)
│   ├── consulta-transacciones/
│   ├── diagnostico-invalidas/
│   └── exportar-reporte/
├── config/                    # PERSONALIZACIÓN
│   ├── sistema.json           #   política de confirmación, límites y decisiones
│   └── agentes/analista.json · auditor.json
├── datos/                     # Archivos de entrada (válidos, con errores y casos de error de archivo)
├── ejemplos/                  # Conversaciones reales y un reporte generado
└── tests/                     # 190 pruebas automatizadas
```

---

## 🔧 Refactorización realizada

El sistema anterior ya separaba normalización, validación y métricas. Lo que seguía **acoplado estaba en la interfaz**, y las skills necesitaban esa lógica. Se extrajo para reutilizarla:

| Problema detectado | Refactorización | Beneficio |
|---|---|---|
| La **validación de los valores de los filtros** vivía dentro de la CLI (`_editar_filtro`) | Pasó a `nucleo/filtros.py` (`parsear_*` y `construir_filtros`) | La CLI y la skill de consulta validan **exactamente igual**, sin duplicar código |
| La **serialización y escritura de resultados** vivía dentro de la CLI (`exportar`) | Pasó a `nucleo/exportacion.py` | La CLI y la skill `exportar-reporte` comparten el mismo código |
| El **formato de tablas y dinero** estaba dentro de la CLI | Pasó a `nucleo/presentacion.py` | Las skills presentan resultados con el mismo formato |
| Todos los módulos mezclados en la raíz | Paquete `nucleo/` (motor) separado de la interfaz y de los agentes | Dependencias en un solo sentido; el motor se puede probar y reutilizar solo |
| El comportamiento solo existía como un menú numérico fijo | **Skills** (capacidades) + **agentes** configurados por JSON | Se añade o cambia un comportamiento sin tocar el motor |

La refactorización **no rompió nada**: las 42 pruebas del sistema anterior siguieron pasando tras mover el código, y la CLI clásica sigue funcionando (`python main.py clasico`).

---

## 🧩 Skills

Una skill es una carpeta autocontenida:

```
skills/diagnostico-invalidas/
├── SKILL.md                    # metadatos (nombre, descripción, palabras clave, efectos) + instrucciones
├── skill.py                    # PARAMETROS (esquema de argumentos) y ejecutar(sesion, **args)
└── recursos/
    ├── guia_motivos.json       # causas probables y correcciones de cada tipo de rechazo
    └── vocabulario.json        # sinónimos para el modo simulado
```

| Skill | Qué hace | Efectos | Recursos |
|---|---|---|---|
| `consulta-transacciones` | Lista, filtra, cuenta y suma transacciones válidas; busca por id | Ninguno (solo lectura) | `vocabulario.json` |
| `diagnostico-invalidas` | Resume los rechazos, detalla un registro, filtra por tipo de problema y propone un plan de corrección | Ninguno (solo lectura) | `guia_motivos.json` (19 tipos de rechazo), `vocabulario.json` |
| `exportar-reporte` | Escribe `reporte.md` y tres JSON | **Escribe archivos** (exige confirmación) | `plantilla_reporte.md` |

**Cumplimiento del estándar de skills.** El formato sigue la especificación abierta *Agent Skills* ([agentskills.io](https://agentskills.io/specification)):

| Requisito del estándar | En este proyecto |
|---|---|
| `SKILL.md` con encabezado YAML que incluye `name` y `description` | ✔ Las tres skills |
| `name`: 1–64 caracteres, minúsculas, dígitos y guiones, sin guión al inicio ni al final ni `--`, igual al nombre de la carpeta | ✔ El cargador lo exige y hay pruebas |
| `description`: 1–1024 caracteres (qué hace y cuándo usarla) | ✔ El cargador lo exige (aquí, además, mínimo 20) |
| Campos opcionales: `license`, `compatibility` (≤ 500), `metadata` | ✔ Los campos propios (`palabras_clave`, `efectos`) van **dentro de `metadata`**; el cargador rechaza claves fuera del estándar |
| Divulgación progresiva (metadatos al arrancar, cuerpo al activar) | ✔ Verificado con pruebas |
| Directorios opcionales `scripts/`, `references/`, `assets/` | ⚠️ **Desviación:** uso `recursos/` y un `skill.py` en la raíz de la skill. El estándar permite directorios adicionales, pero no es la convención |

Además, el parser de encabezados es **mínimo** (clave: valor y un nivel de bloque): cubre lo que necesita el estándar, pero no es un parser YAML completo.

**Divulgación progresiva.** Al arrancar solo se leen los metadatos de cada skill. El agente "ve" únicamente su **nombre y descripción**; el cuerpo de `SKILL.md` se carga cuando la skill se elige. Las pruebas lo verifican: tras arrancar no hay ninguna skill con instrucciones cargadas, y después de una consulta solo la usada.

**Validación al cargar.** Una skill mal definida falla con un mensaje claro: falta `SKILL.md` o `skill.py`, `name` distinto de la carpeta o en formato inválido, descripción fuera de 20–1024 caracteres, sin palabras clave, efecto desconocido, parámetros mal declarados, cuerpo vacío, o una skill con efectos sin función `previsualizar`.

---

## 🎭 Agentes y personalización

El código del agente es **el mismo** para todos. Lo que los distingue está en `config/agentes/*.json`:

| | **Analista** | **Auditor** |
|---|---|---|
| Rol | Analista de transacciones | Auditor de calidad de datos |
| Skills permitidas | `consulta-transacciones`, `exportar-reporte` | `diagnostico-invalidas`, `exportar-reporte` |
| Tono | Conciso, numérico y directo | Formal, riguroso y didáctico |
| Prefijo de respuesta | `[Analista]` | `[Auditor] Informe de calidad de datos` |
| Muestra recomendaciones | No | Sí |
| Reglas de comportamiento | Cifras exactas; no mezclar monedas; derivar lo de inválidas | Apoyarse en la guía; no corregir por su cuenta; derivar lo de válidas |

**Un mismo mensaje, dos agentes:** pedir a cualquiera algo que no es suyo no ejecuta nada y deriva al agente correcto:

```
[Analista] > por qué se rechazaron los registros inválidos
Eso corresponde a la skill 'diagnostico-invalidas', que no está disponible para Analista.
Cambia de agente con /agente auditor.
```

**Prompt estructurado.** Cada agente construye su prompt con secciones fijas: `ROL`, `OBJETIVO`, `TONO`, `REGLAS DE COMPORTAMIENTO`, `SKILLS DISPONIBLES`, `POLÍTICA DE EFECTOS` y `FORMATO DE RESPUESTA`. Se puede ver con `/prompt`.

**Cambiar la configuración cambia el comportamiento sin tocar código** (hay una prueba que lo comprueba: activar `mostrar_recomendacion` en el Analista hace que aparezcan las sugerencias).

---

## 🛡️ Seguridad: guardas y confirmación

Un modelo puede equivocarse o ser manipulado, así que **el agente no ejecuta a ciegas**:

1. **Guardas** (`agentes/guardas.py`): la acción propuesta debe tener forma válida, apuntar a una skill que **exista y esté permitida para ese agente**, y usar solo **argumentos declarados** con el **tipo** correcto. Si no, no se ejecuta nada.
2. **Confirmación de efectos:** una skill que escribe archivos **siempre** pide confirmación antes de ejecutarse. La política la aplica **el agente, no el modelo**: un modelo no puede saltársela ni inventar un argumento `confirmado`.
3. **Rutas seguras:** `exportar-reporte` solo escribe en carpetas **relativas dentro del proyecto**. Rechaza rutas absolutas, `..`, `~`, unidades de disco y enlaces simbólicos que escapen.
4. **Fallos controlados:** si el modelo o una skill lanzan una excepción, el agente informa el error en lugar de caerse.
5. **Cargar otro archivo** (`/cargar`) también pide confirmación cuando ya hay datos cargados.

---

## 🔌 Conectar un LLM real

`agentes/llm.py` define el contrato `ClienteLLM` con dos métodos:

- `decidir(prompt, historial, catalogo)` → devuelve una acción, por ejemplo `{"accion": "skill", "skill": "consulta-transacciones", "args": {...}}`.
- `redactar(prompt, historial, resultado, comportamiento)` → devuelve el texto final.

El proyecto incluye un cliente real para Google Gemini:

```bash
# Windows PowerShell
$env:GEMINI_API_KEY="tu_clave"
$env:GEMINI_MODEL="gemini-3.8-flash"   # opcional; ese es también el modelo predeterminado
python main.py --llm gemini datos/transacciones_validas.json
```

También puedes activar Gemini automáticamente definiendo `GEMINI_API_KEY` y ejecutar `python main.py` sin `--llm`. Para volver al modo determinista:

```bash
python main.py --llm simulado datos/transacciones_validas.json
```

`ClienteGemini.decidir()` envía el prompt, el historial y el catálogo al API de Gemini y exige una respuesta JSON; `redactar()` genera el texto final respetando la configuración del agente. El agente no cambia: las guardas siguen validando toda acción antes de ejecutarla. Si Gemini responde HTTP 503 por alta demanda, el servicio está temporalmente ocupado: espera un momento y vuelve a intentar. La suite local no necesita ni utiliza una API key.

---

## ⚖️ Decisiones: mías y propuestas de la IA

La consigna pide **uso consciente de la IA como apoyo**, con las decisiones claras. Quedan registradas en [`config/sistema.json`](config/sistema.json):

| Decisión | Origen |
|---|---|
| Base: el sistema de transacciones, al que se le agrega una capa agéntica con skills | **Mía** |
| Dos agentes: **Analista** (consultas y métricas) y **Auditor** (validación e inválidas) | **Mía** |
| Skills `consulta-transacciones` y `diagnostico-invalidas` | **Mía** |
| **Siempre pedir confirmación** antes de escribir archivos o cargar otro archivo | **Mía** |
| LLM en modo simulado, sin API key | **Mía** |
| Skill `exportar-reporte` (la única con efectos) | Propuesta de la IA |
| Divulgación progresiva de las instrucciones de las skills | Propuesta de la IA |
| Guardas que validan las acciones del modelo | Propuesta de la IA |
| La política de confirmación la aplica el agente, no el modelo | Propuesta de la IA |
| Exportación solo a rutas relativas dentro del proyecto | Propuesta de la IA |
| Límites de montos y fechas inclusivos | Propuesta de la IA |
| Derivar al otro agente lo que está fuera de alcance | Propuesta de la IA |
| Las "métricas" del Analista son conteos y totales de lo consultado | Propuesta de la IA |

**Una consecuencia de mis decisiones:** el Analista se definió como «consultas y métricas», pero no elegí la skill `resumen-metricas`. Por eso sus métricas son los conteos y totales por moneda de cada consulta, y el reporte completo sale con `exportar-reporte`. Agregar esa skill es sencillo si se quisiera.

---

## 💬 Ejemplo de conversación

Salida real del sistema (modo simulado), con la ruta de la carpeta abreviada como `(…)`. Las conversaciones completas están en [`ejemplos/`](ejemplos/).

```
[Analista] > cuánto suman las transacciones en dólares
[Analista]
6 transacciones cumplen: moneda: USD.
  Moneda   Cant.           Total    Confirmado (SUCCESS)
  USD          6        7,885.56                1,401.00

[Analista] > exporta el reporte
Voy a escribir 4 archivos en 'salida_agente' (…): reporte.md, normalizadas.json, invalidas.json, metricas.json.
¿Confirmas? (s/n)
> n
Acción cancelada. No se escribió nada.
```

---

## 🧪 Pruebas

**190 pruebas automatizadas** (`python -m unittest discover -s tests -v`). Los valores esperados se calcularon **a mano** a partir de los archivos de datos antes de ejecutar. Las pruebas del cliente Gemini usan respuestas simuladas; no llaman al API real.

| Archivo de pruebas | Pruebas | Qué verifica |
|---|---:|---|
| `test_normalizacion` | 10 | Montos, fechas, estados y detección de fuente |
| `test_procesamiento` | 16 | Los archivos de datos de punta a punta, métricas y errores de archivo |
| `test_interfaz` | 16 | La CLI clásica (sigue funcionando tras la refactorización) |
| `test_nucleo_refactor` | 13 | Los módulos extraídos: filtros, presentación y exportación |
| `test_skills_carga` | 35 | Validación de skills (incluido el estándar de `SKILL.md`) y de la configuración de agentes; divulgación progresiva |
| `test_skills_ejecucion` | 29 | Cada skill con valores esperados, rutas inseguras y enlaces simbólicos |
| `test_llm_simulado` | 21 | Elección de skill, extracción de argumentos y pruebas del cliente Gemini sin llamadas de red |
| `test_agente` | 30 | Personalización, derivación, confirmación y guardas ante un modelo que se equivoca |
| `test_chat` | 20 | El chat y `main` simulando al usuario |

**¿Detectan errores de verdad?** Para comprobarlo se rompió el código a propósito, de a una cosa, y se verificó si las pruebas lo notaban. Se probaron **16 modificaciones** (saltarse la confirmación, aceptar `..`, permitir una skill no autorizada, aceptar montos en cero, ids duplicados, etc.). Al principio detectaron 14: las dos que pasaron revelaron un hueco real (`sub/../otra` no estaba probado) y una protección redundante en el código. Se corrigieron ambas y **las 16 se detectan**.

### Pruebas manuales

Marcar al completarlas:

- [x] Hablé con el Analista y el Auditor y probé al menos tres consultas distintas con cada uno.
- [x] Pedí algo fuera del alcance de un agente y comprobé que me derivó al otro.
- [x] Probé `exporta el reporte`, respondí `n` y verifiqué que no se creó ninguna carpeta; luego respondí `s` y revisé `reporte.md`.
- [x] Edité `config/agentes/analista.json` (por ejemplo `mostrar_recomendacion`) y comprobé que cambió su comportamiento.
- [x] Usé `/prompt` y `/traza` para ver cómo decide el agente.

---

## 🧾 Uso de la IA y ajustes sobre sus sugerencias

**La IA** escribió el código y propuso la arquitectura. **Yo** decidí la base del proyecto, los dos agentes, las skills elegidas, la política de confirmación y el uso del modo simulado (tabla de decisiones).

**Defectos que aparecieron al revisar la salida real y las propias pruebas** (y que se corrigieron con prueba):

| Hallazgo | Ajuste |
|---|---|
| El saludo quedaba mal redactado («Hola, soy Analista, analista de transacciones. Responder consultas…») | Los saludos se arman con una frase completa a partir del objetivo |
| El plan de corrección decía «(1 registros)» | Concordancia singular y plural |
| Tras cancelar una exportación, `/traza` perdía los pasos previos | La traza de una confirmación conserva la decisión y la política que la pidió |
| El reporte generado incluía la **ruta absoluta** del archivo (no portable y expone carpetas del equipo) | Solo se muestra el nombre del archivo |
| Dos de las propias pruebas **no probaban nada** (aserciones que siempre se cumplían) | Se reemplazaron por aserciones reales |
| El *mutation testing* mostró un hueco de pruebas y una redundancia | Se añadió la prueba y se eliminó la redundancia |

---

## ⚠️ Limitaciones conocidas

- **El modelo es simulado.** Elige la skill por palabras clave y extrae argumentos con expresiones regulares: entiende bien los ejemplos documentados, pero no el lenguaje libre. Una frase ambigua puede ir a la skill equivocada o a «no entendido».
- Los números en las consultas se escriben **sin separador de miles** (`1000`, no `1,000`).
- El Analista **no tiene una skill de métricas globales**; el reporte exportado las incluye.
- El cliente Gemini requiere conexión, una API key válida y disponibilidad/cuota del servicio. Una respuesta HTTP 503 puede indicar alta demanda temporal.
- Las exportaciones usan la fecha y hora del equipo, por lo que `reporte.md` cambia en cada ejecución.

---

*Desarrollado con IA como herramienta de apoyo · KODIGO Academy*
