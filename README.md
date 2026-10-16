# Brighter IA local — monitor, comparación y detección de licitaciones

Rastrea oportunidades públicas y compras del Estado peruano relacionadas al
rubro de Brighter Peru: pantallas interactivas, pizarras digitales, kioscos
y tótems, y equipamiento audiovisual. Combina **cuatro fuentes** con
metodologías distintas — SEACE (licitaciones abiertas), Perú Compras
(catálogo de Acuerdo Marco), PetroPerú (avisos tempranos de régimen propio)
y Banco de la Nación (bases de licitaciones y concursos de régimen propio) —
y las presenta en un dashboard interactivo.

> Derivado del monitor de licitaciones original. Se quitó lo pensado para la
> nube (GitHub Actions, Streamlit Cloud, `packages.txt`) y se añadió una capa
> de **IA local** (`src/ia/`) que corre en tu equipo con Ollama. Contexto
> técnico heredado: `docs/CONTEXTO_ORIGEN.md`.

## IA local

En Windows: doble clic en `iniciar.bat` (crea `.venv`, instala dependencias, comprueba Ollama y abre el tablero). Otras acciones: `iniciar.bat comprobar | demo | tests`. En el panel de expediente aparece la casilla «Usar IA local».

```bash
# 1. Instalar Ollama (https://ollama.com) y bajar un modelo
ollama pull qwen2.5:7b-instruct
# 2. Comprobar
python src/ia/comprobar_ia.py
# 3. Probar la comparación explicada por el modelo
python src/analizar_ia.py --demo
# 4. Tests de la capa (no necesitan modelo)
python tests/test_ia.py
```

Reparto de responsabilidades (decisión de diseño):

| tarea | quién la hace |
|---|---|
| Extraer requerimiento del texto de las bases | reglas (`extractor.py`) **y** IA (`ia/extraer_llm.py`); `comparar_con_reglas()` muestra dónde discrepan |
| Detectar si una convocatoria es panel interactivo | palabras clave + IA (`ia/clasificar_llm.py`) |
| Dictamen cumple / no cumple | **solo reglas** (`evaluar_licitacion.py`) |
| Redactar la explicación | IA (`ia/explicar.py`), sobre la tabla ya calculada |

La IA nunca cambia un veredicto, y todo dato que extrae debe figurar en el
texto; si no, se descarta. Modelo, URL y contexto se editan en `config.yaml`
(`ia_local`). Las variables `BRIGHTER_SALIDA` y `ENTIDAD_OBJETIVO` controlan el
reporte de competencia.

---

## Prototipo: alerta diaria, predictor de postores y asistente

Necesita `data/analisis.db` (cópiala de tu repo original o genérala con
`python src/postores.py --anios 2023 2024 2025 2026 --solo INTERACTIVA`).

| qué | cómo | para qué |
|---|---|---|
| Alerta diaria | `iniciar.bat alerta` | baja vigentes, la IA descarta falsos positivos, cruza el tamaño con las fichas, estima competidores y redacta; deja `data/alertas/alerta_AAAA-MM-DD.md` |
| Predictor de postores | `src/ml/predictor.py` | probabilidad de que cada empresa se presente a un proceso nuevo; puede usar «ya sé que se presentó X» |
| Validación | `iniciar.bat validar` | entrena con el pasado, prueba en el año más reciente y compara contra «las más frecuentes». Solo declara mejora si el intervalo de confianza queda sobre cero |
| Asociaciones | `src/ml/asociaciones.py` | pares que se presentan juntos (lift, P(B\|A), q-valor) y si el patrón se sostiene después |
| Gráficos del ruido de datos | `iniciar.bat graficos` | 6 PNG en `data/graficos/`: campos vacíos, embudo de vigentes, ruido de rubro, montos extremos, órdenes resueltas y cobertura en el tiempo. Si existe `analisis.db` añade postores por proceso y año |
| Preguntar en español | `iniciar.bat preguntar` o `iniciar.bat asistente` | la IA genera SQL de solo lectura; las consultas que confirmas se guardan y se reutilizan como ejemplos |

Cómo se corresponde con el esquema de aprendizaje: huecos → imputación con
indicador «faltaba» (no se inventa el dato); palabras → números → variables
numéricas y vectores; escalas → `StandardScaler`; quitar lo inútil →
`VarianceThreshold`; modelo → regresión logística (probabilidades); decidir →
ranking; comprobar → `validar.py`.

Dos cautelas: con pocos procesos (menos de ~15 de prueba) la validación dice
«no concluyente»; y un par de empresas que se juntan más que el azar puede
simplemente operar en la misma región, no es evidencia de concertación.

Sin tu base real, `python src/ml/validar.py --sintetico` (con estructura) y
`--sintetico --azar` (azar puro) permiten comprobar que el método detecta lo
que existe y no inventa lo que no.

## Pendiente de pulir (extracción de bases)

La extracción del requerimiento es el cuello de botella (4 de 23 expedientes
legibles). Orden sugerido: (1) medir con `comparar_con_reglas()` sobre los
bloques ya localizados cuántos campos aporta la IA que las reglas no ven;
(2) mejorar la localización del bloque antes que el modelo; (3) ampliar el
ground truth manual más allá de 3 expedientes para medir de verdad.

---

## Instalación
```bash
pip install -r requirements.txt
```

## Uso

1) Extraer histórico de SEACE (descarga los años definidos en `config.yaml` y llena la base):
```bash
python src/extract.py
```
O probar sin descargar, con la muestra incluida:
```bash
python src/_muestra.py            # genera data/muestra.jsonl
python src/extract.py --archivo data/muestra.jsonl
```

2) Traer oportunidades **vigentes** de SEACE (a las que se puede postular ahora):
```bash
python src/vigentes.py
```

3) Traer catálogo de **Perú Compras** (Acuerdo Marco — compras ya ejecutadas):
```bash
python src/perucompras.py
```

4) Traer avisos de **PetroPerú** (señal temprana, antes de proceso formal):
```bash
python src/petroperu.py
```

5) Traer bases de **Banco de la Nación** (licitaciones y concursos, régimen propio):
```bash
python src/bnacion.py
```

6) Ver el dashboard:
```bash
python -m streamlit run src/dashboard.py
```
(usa `python -m streamlit` si el comando `streamlit` no está en el PATH de tu terminal)

## Antes de empezar: comprobar el entorno

```bash
python src/comprobar_entorno.py
```

Dice qué paquetes y herramientas faltan, con el comando exacto para
instalarlos, y separa lo imprescindible de lo opcional. El dashboard y los
cuatro extractores funcionan sin OCR ni lector de RAR; esos dos solo hacen
falta para el pipeline de especificaciones.

## Pipeline de especificaciones (bloque nuevo)

Va de una licitación a la pregunta "¿qué marcas podían presentarse?".

7) Listar los documentos de adjudicación de los procesos del rubro, a partir
   de los paquetes OCDS ya descargados en `data/`:
```bash
python src/buscar_actas.py --anio 2025 --solo INTERACTIVA
```
Escribe un CSV con el `fileCode` de cada documento. Sin `--solo` incluye todo
el rubro audiovisual, que es mucho más amplio que los paneles interactivos.

8) Descargar y abrir un documento del expediente (PDF suelto, .rar, .zip o
   contenedor anidado: se detecta por firma de bytes, no por extensión):
```bash
python src/descargar_documento.py --filecode <uuid> --extraer tmp/exp1
python src/contenedores.py --diagnostico      # con qué se pueden abrir los .rar
```

9) (Opcional) Indexar los documentos del expediente del histórico, una sola vez por
   año. Deja la tabla `documentos` en `analisis.db`. **El Comparador BTOUCH ya no
   lo necesita** (consulta cada proceso vigente por separado, ver más abajo); sirve
   solo si quieres analizar procesos históricos con `panel_expediente.render`:
```bash
python src/indexar_documentos.py --anios 2025 2026
```

10) Historial de postores: qué empresas se presentan, cuántas veces y contra
    quién. Sale del OCDS, sin descargar ni leer PDF:
```bash
python src/postores.py --anios 2023 2024 2025 2026 --solo INTERACTIVA
python src/postores.py --informe --csv data/postores.csv
```

11) Reporte de inteligencia competitiva en Excel, a partir de lo que dejó el
    paso anterior. Un libro con una hoja por nivel de agregación: empresas,
    participaciones crudas, procesos, coincidencias entre empresas, indicadores
    y matriz año por año.
```bash
python src/reporte_competencia.py
python src/reporte_competencia.py --anios 2024 2025 2026
python src/reporte_competencia.py --salida "C:/ruta/archivo.xlsx"
```
    El libro **no** se escribe dentro del repositorio. Por defecto va a la
    carpeta del estudio de mercado y, si no existe, a `tmp/`, que está
    ignorada por git. Dos lecturas obligatorias antes de usar sus números:
    un año con muchas menos participaciones por proceso no tuvo menos
    competencia, publicó peor la lista de postores; y la columna «exceso sobre
    lo esperado» mide rareza estadística frente a un reparto al azar, no
    concertación, porque ese modelo ignora que las empresas se concentran por
    región, tipo de proceso y rango de monto. Sirve para priorizar qué
    expediente leer. La hoja 00 del propio libro repite ambas advertencias.

12) Evaluar un requerimiento contra las fichas de BTOUCH y de la competencia:
```bash
python src/fichas.py                                    # inventario de fichas
python src/evaluar_licitacion.py --demo                 # ejemplo de 86"
python src/evaluar_licitacion.py --json data/resultado_extractor.json --resumen
python src/evaluar_licitacion.py --json data/resultado_extractor.json --expediente 7
```

Qué hace cada módulo nuevo:

- `src/comprobar_entorno.py` — qué falta instalar en este equipo
- `src/contenedores.py` — identifica y abre lo que devuelve SEACE, y elige qué
  documento del expediente le interesa al extractor
- `src/descargar_documento.py` — descarga por `fileCode` (GET directo, sin sesión)
- `src/buscar_actas.py` — localiza documentos de adjudicación y clasifica por
  categoría de producto
- `src/ocr.py` — texto nativo o OCR según haga falta, con caché
- `src/extractor.py` — saca el requerimiento técnico en 18 campos
- `src/fichas.py` — fichas estructuradas de BTOUCH y competidores
- `src/evaluar_licitacion.py` — compara exigido contra ficha y dictamina
- `src/indexar_documentos.py` — (opcional) vuelca los documentos del OCDS a la tabla `documentos`
- `src/ficha_seace.py` — consulta la ficha de UN proceso vigente (documentos, ítems, cronograma) con caché de 24 h
- `src/postores.py` — historial de participantes por empresa, con RUC
- `src/reporte_competencia.py` — libro Excel de inteligencia competitiva a
  partir de la tabla `postores`, con cobertura por año y coincidencias entre
  empresas; escribe fuera del repositorio
- `src/panel_expediente.py` — el panel del tablero: ficha del proceso y, detrás de
  un botón, descarga, lectura y comparación contra BTOUCH

Leer la sección 11 de `PROJECT_CONTEXT.md` antes de usarlo: la marca del
producto adjudicado **no** se publica en los documentos de SEACE, y el motor de
evaluación existe precisamente porque ese dato hay que inferirlo.

## Configuración
Edita `config.yaml` para cambiar palabras clave, exclusiones, años y el
Acuerdo Marco de Perú Compras a monitorear — sin tocar código.

## Estructura
- `config.yaml` — palabras clave, exclusiones y filtros (editable por no-programadores)
- `src/extract.py` — extractor OCDS histórico (SEACE/OECE) + dedup + tipo de licitación + SQLite
- `src/vigentes.py` — extractor de oportunidades vigentes (API SEACE en vivo)
- `src/perucompras.py` — extractor de órdenes por Acuerdo Marco (Perú Compras)
- `src/petroperu.py` — extractor de avisos de contratación futura (PetroPerú)
- `src/bnacion.py` — extractor de bases de licitaciones y concursos (Banco de la Nación)
- `src/dashboard.py` — tablero Streamlit (4 fuentes, búsqueda avanzada por fuente) + export Excel con formato
- `src/_muestra.py` — genera datos de prueba
- `src/reporte_competencia.py` — reporte Excel de competencia (salida fuera del repositorio)
- `data/` — base SQLite (`licitaciones.db`, sí se versiona) y descargas crudas (no se versionan)
- `src/ia/` — capa de IA local (cliente Ollama, extracción, clasificación, explicación)
- `tests/test_ia.py` — pruebas de la capa de IA con servidor simulado
- `src/estilo.py` — apariencia común (modo claro y oscuro); `src/ia/equipo.py` — especificaciones del equipo y qué modelos le caben
- `tests/test_interfaz.py` — pruebas del chat, la configuración y los colores
- `src/ia/procesos.py` — preguntas sobre un proceso concreto (plazos, ficha) resueltas por reglas con la tabla `vigentes`, sin IA; `tests/test_procesos.py` las prueba
- `PROJECT_CONTEXT.md` — memoria técnica completa del proyecto (leer primero)

## Qué se ha logrado

**Fuente SEACE (licitaciones abiertas)**
- Extractor histórico OCDS con deduplicación por `ocid` y purga de filas
  obsoletas en cada corrida (sin arrastrar datos de configuraciones viejas).
- Extractor de oportunidades vigentes contra la API pública en vivo de SEACE.
- Matcher de palabras clave con límites de palabra reales (evita falsos
  positivos como "monitor" dentro de "monitoreo") y tolerancia a plurales.
- Aislamiento de coincidencias por ítem: en procesos con múltiples ítems no
  relacionados, ya no se permite que dos ítems distintos se combinen para
  simular una coincidencia falsa.
- Detección best-effort de marca/modelo por regex sobre el texto del ítem.
- Campo "Tipo de licitación" (Licitación Pública, Adjudicación Simplificada,
  etc.), tomado del método de contratación OCDS o deducido del prefijo de
  la nomenclatura si el dato no viene en el registro.

**Fuente Perú Compras (Acuerdo Marco)**
- Investigación y documentación del endpoint real
  (`consultaOrdenes`, formato de body y respuesta propietarios — no JSON).
- Extractor funcional para el Acuerdo Marco 322-BIENES (Equipos Multimedia
  y Accesorios).
- Aclarado en el dashboard que esto es catálogo de compras ya ejecutadas
  (inteligencia de mercado), no licitaciones abiertas a las que postular.
- Columna "Tipo de contratación" visible en el dashboard.

**Fuente PetroPerú (señal temprana)**
- Extractor de avisos de contratación futura (antes de que exista un
  proceso formal en el portal propio de PetroPerú).
- Parser de fechas en español (formato "17-Ago-2026") propio del portal.

**Fuente Banco de la Nación (régimen propio)**
- Extractor de bases de licitaciones y concursos ya publicadas.
- Columna "Tipo de proceso" visible en el dashboard.

**Dashboard**
- Navegación por botones entre las 4 fuentes (metodologías distintas,
  separadas intencionalmente).
- Panel editable de palabras clave/exclusiones directamente desde la barra
  lateral, sin tocar `config.yaml`.
- Búsqueda avanzada por fuente: tamaño de pantalla en pulgadas, categoría
  de producto, precio/monto, proveedor o marca, rango de fechas y, según
  la fuente, departamento o tipo de proceso — todos combinables en AND,
  con contador "X de Y" resultados.
- Estado con colores (verde/amarillo/rojo) y columna de días restantes en
  SEACE Vigentes; estado de entrega coloreado en Perú Compras.
- Exportación a Excel con formato: cabecera en color y negrita, columnas
  auto-ajustadas, panel superior fijo, autofiltro y el mismo color
  condicional por fila que se ve en pantalla (donde aplica).
- Nota conocida: los filtros de tamaño/categoría solo leen el texto que
  trae el propio registro de la convocatoria (título/objeto), no el
  contenido de los PDFs adjuntos (bases, ficha técnica) — ver
  `PROJECT_CONTEXT.md` para más detalle.

**Infraestructura**
- Repositorio limpio: archivos pesados de descarga cruda (`.jsonl.gz`,
  100MB+) fuera de git vía `.gitignore`; la base filtrada (`licitaciones.db`)
  sí se versiona para que el despliegue en Streamlit Cloud tenga datos
  sin necesidad de procesar nada en la nube.
- Actualización de datos: ejecutar los extractores a mano o con el programador de tareas del sistema.

## Pendiente
- Extraer texto de los PDFs adjuntos (bases, ficha técnica) para que la
  búsqueda avanzada también encuentre especificaciones que no están en el
  título/objeto del registro.
- Alerta por correo si un extractor falla.
- Explorar si Perú Compras tiene una sección de convocatoria para nuevos
  proveedores (pausado — enlaces encontrados hasta ahora están caídos).
- Explorar SEDAPAL, ENAPU y CORPAC como fuentes adicionales (pausado —
  sin acceso público funcional al momento de revisar).

Datos: OCDS / OECE (ex OSCE), Perú Compras, PetroPerú y Banco de la Nación,
licencia CC BY 4.0.



## El Asistente IA: chat, configuración y tema

El botón **🤖 Asistente IA** abre una pantalla con el **chat al centro** y cuatro secciones:

| sección | qué hay |
|---|---|
| 💬 Chat | conversación con historial. Al empezar muestra globos de sugerencia (tocar uno hace la pregunta); después quedan en «💡 Ideas». Las respuestas del glosario/ranking se marcan como tal; las de datos traen su tabla y «Cómo lo obtuve» (SQL) para verificar y «aprender» la consulta |
| 📬 Alerta de hoy | la última alerta de `data/alertas/` |
| 🎯 Competidores | probabilidad de que cada empresa se presente a un proceso parecido |
| ⚙️ Configuración | **especificaciones del equipo** (procesador, memoria libre/total, tarjeta de video, disco), modelo recomendado según la memoria, elección de modelo/dispositivo/contexto, prueba de velocidad, descarga de modelos con su ajuste al equipo (✅ cómodo · ⚠️ justo · ⛔ pesado), dónde corre el modelo ahora y qué conoce la IA (glosario, empresas, marcas, participaciones) |

Sin Ollama el chat sigue respondiendo lo que está en la base de conocimiento.

**Preguntas por un proceso.** Si citas la nomenclatura (`¿cuántos días quedan en CONV-PROC-23-2026-UNSA.-1?`, `¿de qué trata LP-SM-14-2026-MDCC-1?`) el asistente no usa la IA: busca el proceso en `vigentes`, calcula con la fecha de hoy (cierre de inscripción y presentación de propuestas) y muestra la ficha. Acepta el código con espacios o en minúsculas, avisa si el proceso ya no está vigente o no existe, y avisa si la lista de vigentes tiene más de una semana.

**Tema claro/oscuro.** Se cambia en el menú ⋮ (arriba a la derecha) → *Settings* → *Theme*.
Los colores base están en `.streamlit/config.toml` (secciones `[theme.light]` y `[theme.dark]`)
y el resto del estilo en `src/estilo.py`. Los colores de estado de las tablas son translúcidos
a propósito: con fondos pastel fijos la letra clara del tema oscuro quedaba ilegible.

Prueba: `python tests/test_interfaz.py` (no necesita Ollama).

## El Comparador BTOUCH dentro del tablero

El botón **Comparador BTOUCH** trabaja sobre los procesos **vigentes del año en curso**
(a los que todavía se puede postular). No descarga paquetes anuales ni necesita un
índice previo:

1. **La lista** sale de la tabla `vigentes` (oportunidades del SEACE, unos pocos MB),
   filtrada al año en curso y al rubro de pantallas y pizarras (con la opción de ver
   todos). Se renueva con **🔄 Actualizar lista**, o con `iniciar.bat vigentes`; una
   vez por semana alcanza. Los procesos que cierran antes aparecen arriba.
2. **Al elegir un proceso** se consulta solo su ficha en el SEACE (unos KB): qué se
   compra, el cronograma y los documentos publicados. La ficha se guarda 24 horas en
   `data/cache_fichas/`. Si no hay conexión se usa la última copia.
3. **El documento** se descarga únicamente al pulsar **Analizar expediente y comparar
   con BTOUCH**: se abre sea cual sea su formato, se lee —con reconocimiento óptico si
   hace falta—, se extrae el requerimiento técnico y se compara contra las fichas de
   BTOUCH y de la competencia. El resultado se guarda en `data/cache_analisis/` para no
   repetirlo.

La ficha de un proceso sale de `https://prod4.seace.gob.pe:8086/api/oportunidades/fichaProceso/idProceso/{id}`
(`src/ficha_seace.py`), el mismo servicio que usa la ficha pública del portal.

Conviene saber que este análisis **falla seguido, y no por un defecto del
panel**: solo cuatro de cada veintitrés expedientes entregan un requerimiento
legible. Cuando no puede, el panel dice en qué paso se detuvo y por qué.
