# Cuaderno de prueba con nuestros datos

Una prueba corta, **hecha con los datos reales del proyecto**, en el mismo estilo que el ejercicio de clase con Iris:
primero se ve cómo están organizados los datos y después se dibuja cómo "piensan" tres modelos.

**Archivo:** `01_organizacion_de_los_datos.ipynb` (ya trae los resultados guardados, se puede leer sin ejecutar nada).
Las imágenes están también sueltas en `img/`.

## Qué muestra

1. **Mapa de los datos** (`img/mapa_datos.png`): las tablas de `analisis.db` y `licitaciones.db`, cuántas filas tiene cada una y por qué llave se conectan (RUC o nomenclatura). También deja ver qué *no* se conecta: por ejemplo, los procesos vigentes casi no coinciden con el histórico.
2. **Frontera de decisión** (`img/fronteras.png`): con las 2 mejores características (`SelectKBest`), cómo parten el espacio una regresión logística, un árbol y un SVC al intentar adivinar si una empresa ganó algún proceso.
3. **Comprobación honesta**: se compara contra un "modelo tonto" que siempre dice *no ganó*, y se mide con exactitud balanceada.

## Qué nos dice sobre los archivos

- Solo el 11 % de las empresas (64 de 589) ganó alguna vez, y la mayoría se presentó una sola vez. Por eso el *accuracy* engaña: el modelo tonto ya saca 0.89.
- Con exactitud balanceada (el azar da 0.50) los tres modelos quedan alrededor de **0.56 a 0.59**: hay una **señal débil**, no concluyente por sí sola.
- Lectura: con solo "cuántos procesos y entidades" no se puede afirmar quién ganará. Sirve, como mucho, para **priorizar**. Es la razón por la que el proyecto deja las decisiones a reglas y da estas estimaciones solo como apoyo (`src/ml/predictor.py`).

## Cómo abrirlo

```
pip install -r requirements.txt
pip install ipykernel
```

Abre el archivo `.ipynb` en VS Code (o con `jupyter notebook`) y ejecuta todo. Solo **lee** las bases, no cambia nada. Si cambian los datos, los números del cuaderno cambian y el veredicto se recalcula solo.

## Límites

Es un ejemplo de aprendizaje con pocos datos: una sola pregunta, dos características y 589 empresas. No sustituye la validación de `src/ml/validar.py`.
