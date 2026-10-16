# Base de conocimiento del asistente

El asistente responde preguntas del tipo «¿qué es X?» **sin pedirle al modelo que invente SQL**.
Busca X en tres lugares, en este orden, y solo redacta con lo que encuentra:

1. `glosario.jsonl` (este directorio, **versionado**): definiciones de términos y de Brighter/BTOUCH.
2. Tabla `marcas` de `data/analisis.db`: marcas de pantallas y qué empresa las ofrece.
3. Tablas `ranking_empresas`, `perfiles_empresas` e `indicadores_empresas` de `data/analisis.db`:
   las 589 empresas postoras, y el perfil de las investigadas una por una.

Si no encuentra nada, el asistente lo dice. No inventa.

## Formato de `glosario.jsonl`

Una línea JSON por término:

    {"termino": "SEACE", "alias": ["otro nombre"], "definicion": "texto", "revisar": false}

- `alias`: otras formas en que alguien podría preguntarlo. Se compara sin tildes ni mayúsculas.
- `revisar`: `true` si es texto sobre la propia empresa que conviene confirmar antes de presentar.

## Cómo agregar conocimiento

- **Un término nuevo:** agrega una línea al glosario. No hay que tocar código.
- **Más empresas o marcas:** actualiza el Excel de ranking y corre
  `iniciar.bat importar` (reconstruye las tablas).

## Qué datos confidenciales hay

`data/analisis.db` y `data/fuentes/` están en `.gitignore`: los perfiles de competidores y el
historial de postores no se suben a GitHub. El glosario sí se versiona; no pongas allí nada confidencial.
