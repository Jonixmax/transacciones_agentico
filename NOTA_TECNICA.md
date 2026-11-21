# Nota técnica: refactorización y personalización agéntica

**Autor:** Jonathan Alberto · **Curso:** AI for Developers Jr. 4 · **IA de apoyo:** Claude (Anthropic)

## 1. Qué se hizo

Se tomó el sistema de normalización de transacciones de la actividad anterior y se le agregó una **capa agéntica**: dos agentes personalizados (**Analista** y **Auditor**) que usan **tres skills propias**. El sistema anterior no usaba LLM, así que no fue una refactorización de un sistema agéntico existente sino la conversión de uno tradicional; lo dejo explícito para evitar confusión.

## 2. Decisiones de diseño

- **Tres capas con dependencia en un solo sentido:** `nucleo/` (motor de datos), `skills/` (capacidades) y `agentes/` (runtime). El motor no sabe que existen agentes.
- **Refactorización del motor:** la validación de filtros, la exportación y el formato de tablas estaban dentro de la interfaz y las skills los necesitaban. Se extrajeron a `nucleo/filtros.py`, `exportacion.py` y `presentacion.py`, de modo que la CLI y las skills comparten el mismo código. Las 42 pruebas previas siguieron pasando.
- **Skills autocontenidas** (`SKILL.md` + `skill.py` + `recursos/`) con divulgación progresiva: el agente solo ve nombre y descripción, y las instrucciones se cargan al elegir la skill.
- **Personalización por configuración:** rol, tono, reglas y skills de cada agente viven en `config/agentes/*.json`; el código del agente es el mismo.
- **Seguridad:** las acciones del modelo se validan antes de ejecutarse, y una skill que escribe archivos siempre pide confirmación. La política la aplica el agente, no el modelo.

## 3. Uso de la IA: qué hizo ella y qué decidí yo

**La IA** escribió el código, propuso la arquitectura y las pruebas. **Yo decidí:** usar el sistema de transacciones como base; los dos agentes (Analista y Auditor); las skills `consulta-transacciones` y `diagnostico-invalidas`; **pedir siempre confirmación** antes de escribir archivos o cargar otro archivo; y comenzar con un modo simulado, sin API key. Después se agregó un cliente para Google Gemini, manteniendo el modo simulado para trabajar localmente. Las demás decisiones (skill de exportación, guardas, rutas seguras, etc.) fueron **propuestas de la IA** y así figuran en `config/sistema.json`. Una consecuencia de mis decisiones: el Analista se definió con «métricas», pero no elegí una skill de métricas, así que sus métricas son los totales de cada consulta.

## 4. Ajustes sobre el código propuesto por la IA

Al revisar la salida real y las propias pruebas aparecieron defectos que se corrigieron con prueba: un saludo mal redactado, el plural «(1 registros)», una traza que perdía pasos al confirmar, un reporte que incluía la **ruta absoluta** del equipo, y **dos pruebas que no probaban nada** (aserciones siempre verdaderas). Además, se rompió el código a propósito en 16 puntos para comprobar que las pruebas lo detectan: detectaron 14; las otras dos revelaron un hueco de pruebas y una protección redundante, ya corregidos (ahora 16 de 16).

## 5. Modos de ejecución

- **Local/simulado:** `python main.py --llm simulado datos/transacciones_con_errores.json`. No necesita conexión ni API key; decide mediante palabras clave y reglas deterministas.
- **Google Gemini:** configura `GEMINI_API_KEY` en PowerShell y ejecuta `python main.py --llm gemini datos/transacciones_con_errores.json`. El modelo predeterminado es `gemini-3.8-flash`; se puede cambiar con `GEMINI_MODEL`.
- Gemini requiere conexión y disponibilidad del servicio. Un HTTP 503 indica que el modelo puede estar temporalmente saturado; espera y vuelve a intentar. Las pruebas automatizadas no llaman a la API real.

## 6. Límites

El modo simulado es un planificador por palabras clave, no un LLM: entiende los ejemplos documentados, no el lenguaje libre. El modo Gemini sí usa un LLM real, pero depende de una API key válida, conexión, cuota y disponibilidad del proveedor.
