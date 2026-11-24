# Evidencias de Seguridad, Recepción y Reparación – Integrante 3 (I3)

## 1. Objetivo

Documentar las funcionalidades implementadas y las pruebas realizadas en los componentes correspondientes a I3 dentro del proyecto Fénix.

El alcance comprende:

- Generación y verificación de firmas HMAC-SHA256.
- Validación temporal y protección contra ataques de repetición (anti-replay).
- Recepción y autenticación de webhooks mediante FastAPI.
- Validación de cabeceras y contenido JSON.
- Reparación de recursos EC2 y S3.
- Pruebas automatizadas de los componentes implementados.

## 2. Seguridad criptográfica

**Archivo:** `src/fenix/utils/crypto.py`

Se implementaron funciones para generar y verificar firmas HMAC-SHA256.

La función `signature()` genera una firma utilizando una clave secreta, un timestamp Unix y el cuerpo original de la solicitud.

La función `verify()` comprueba la autenticidad e integridad del mensaje mediante las siguientes validaciones:

1. Verificación del formato de la firma.
2. Validación del timestamp.
3. Comprobación de una ventana temporal de ±300 segundos.
4. Cálculo de la firma esperada.
5. Comparación segura mediante `hmac.compare_digest()`.

También se dispone de `generate_signature()` como función auxiliar para generar firmas directamente sobre un payload.

La validación temporal impide aceptar solicitudes firmadas cuyo timestamp se encuentre fuera de la ventana permitida.

## 3. Recepción de webhooks

**Archivo:** `src/fenix/services/receiver.py`

Se implementó el endpoint HTTP:

`POST /webhook`

El receptor utiliza la cabecera `X-Webhook-Signature`, con el formato:

`t={timestamp},v1={digest}`

El procesamiento incluye:

1. Comprobación de la configuración del secreto.
2. Validación de la cabecera de autenticación.
3. Lectura del cuerpo original en bytes.
4. Verificación de la firma HMAC.
5. Validación del timestamp.
6. Decodificación y validación del contenido JSON.
7. Publicación del evento autenticado mediante el servicio SQS.

La publicación se realiza únicamente después de superar las validaciones correspondientes.

### 3.1. Respuestas HTTP

| Situación | Respuesta |
|---|---|
| Solicitud válida y publicada | HTTP 202 |
| Firma ausente o incorrecta | HTTP 401 |
| Timestamp fuera de la ventana permitida | HTTP 401 |
| Cabecera de autenticación inválida | HTTP 401 |
| JSON malformado | HTTP 400 |
| JSON que no representa un objeto | HTTP 422 |
| Secreto no configurado | HTTP 500 |
| Error inesperado de procesamiento | HTTP 500 |

## 4. Reparación de recursos

**Archivo:** `src/fenix/services/remediation.py`

Dentro de este módulo, el alcance de I3 comprende la función `repair()`, encargada de aplicar correcciones sobre recursos EC2 y S3.

### 4.1. Reparación de instancias EC2

Para instancias detenidas:

- Se solicita el inicio mediante `start_instances()`.
- Se consulta nuevamente el estado de la instancia.
- Se comprueba que el estado informado sea `running`.
- Si todavía no alcanzó ese estado, se genera un error recuperable (`RetryableError`).
- La reparación solo se confirma cuando se verifica el estado esperado.

Si la instancia ya se encuentra funcionando, no es necesario iniciar nuevamente la operación.

### 4.2. Reparación de etiquetas S3

Para buckets con etiquetas faltantes o incorrectas:

- Se consultan las etiquetas actuales.
- Se obtienen las etiquetas esperadas desde `expected_tags`.
- Se combinan ambos conjuntos para conservar las etiquetas existentes que no pertenecen a las esperadas.
- Se actualizan únicamente los valores necesarios.
- Se vuelve a consultar el bucket para verificar el resultado.

Si las etiquetas ya son correctas, no se realiza ninguna escritura.

La reparación se confirma únicamente después de verificar que las etiquetas aplicadas coinciden con las esperadas.

## 5. Integración con AWS SQS

El receptor utiliza las funciones `publish()` y `queue_url()` del módulo `src/fenix/services/sqs.py`, correspondiente a I2.

La integración permite enviar a la cola los eventos que superaron las validaciones de seguridad y estructura.

La implementación de I3 contempla la autenticación y validación previa a la publicación. La administración de la cola y su mecanismo de publicación pertenecen al componente de I2.

## 6. Pruebas automatizadas

Las siguientes pruebas se ejecutaron desde el entorno virtual del proyecto mediante `pytest`.

### 6.1. Criptografía

**Archivo:** `tests/test_crypto.py`

Comando:

```bash
python -m pytest tests/test_crypto.py -v
```

Resultado: **4 pruebas aprobadas.**

Se verificaron los siguientes casos:

- Generación y verificación de firmas.
- Rechazo de timestamps vencidos.
- Rechazo de timestamps futuros.
- Rechazo de formatos de timestamp inválidos.

### 6.2. Reparación EC2 y S3

**Archivo:** `tests/test_remediation.py`

Comando:

```bash
python -m pytest tests/test_remediation.py -v
```

Resultado: **4 pruebas aprobadas.**

Se verificaron los siguientes casos:

- Confirmación de EC2 después de verificar el estado `running`.
- Rechazo de la reparación cuando EC2 todavía no está funcionando.
- Conservación de etiquetas existentes y verificación de la actualización en S3.
- Ausencia de escrituras cuando las etiquetas ya son correctas.

### 6.3. Recepción de webhooks

**Archivo:** `tests/test_fenix.py`

Comando:

```bash
python -m pytest tests/test_fenix.py -k "missing_signature or altered_signature or old_timestamp or malformed_json or json_list or unknown_resource_alias or additional_field" -v
```

Resultado: **7 pruebas aprobadas.**

Se verificaron los siguientes escenarios:

- Rechazo de solicitudes sin firma.
- Rechazo de firmas alteradas.
- Rechazo de timestamps vencidos.
- Rechazo de JSON malformado.
- Rechazo de JSON que no representa un objeto.
- Rechazo de alias de recursos desconocidos.
- Rechazo de campos adicionales no permitidos.

Estas pruebas se seleccionaron específicamente para documentar los controles de recepción y validación, sin incluir otros escenarios de integración.

### 6.4. Resumen de pruebas específicas

| Componente | Pruebas aprobadas |
|---|---:|
| Criptografía | 4 |
| Reparación EC2 y S3 | 4 |
| Recepción de webhooks | 7 |
| **Total** | **15** |

Las 15 pruebas específicas finalizaron correctamente.

### 6.5. Estado de la batería general

También se ejecutó la batería completa:

```bash
python -m pytest tests/ -v
```

Resultado registrado: **45 pruebas recopiladas, 38 aprobadas y 7 fallidas.**

Los fallos identificados corresponden a distintos escenarios de integración y componentes del proyecto:

- Una prueba utiliza un timestamp fijo (`1000`), incompatible con la ventana anti-replay actual.
- Existen pruebas relacionadas con el flujo de `handle()` y las notificaciones.
- Se identificó un fallo relacionado con la rotación de logs.
- Una prueba de integración requiere LocalStack disponible en `localhost:4566`.

Estos resultados se documentan por separado y no modifican los resultados de las 15 pruebas específicas presentadas anteriormente.

## 7. Evidencias visuales

Las capturas de resultados se encuentran en:

`evidencias/integrante-3/images/`

Se incluyen únicamente resultados de pruebas ejecutadas en el proyecto, sin capturas ilustrativas ni imágenes de código fuente.

| Archivo | Contenido |
|---|---|
| `01-i3-crypto-tests.png` | Resultado de las cuatro pruebas de criptografía. |
| `02-i3-remediation-tests.png` | Resultado de las cuatro pruebas de reparación EC2 y S3. |
| `03-i3-receiver-tests.png` | Resultado de las siete pruebas de recepción y validación. |

## 8. Archivos correspondientes a I3

| Archivo | Funcionalidad |
|---|---|
| `src/fenix/utils/crypto.py` | Generación y verificación de firmas HMAC-SHA256. |
| `src/fenix/services/receiver.py` | Recepción, autenticación y validación de webhooks. |
| `src/fenix/services/remediation.py` | Función `repair()` para recursos EC2 y S3. |
| `tests/test_crypto.py` | Pruebas de criptografía. |
| `tests/test_remediation.py` | Pruebas de reparación de recursos. |
| `tests/test_fenix.py` | Pruebas integradas utilizadas para verificar escenarios del receptor. |

La función `handle()` y la administración de SQS no forman parte del alcance de implementación documentado para I3.

## 9. Consideraciones técnicas

- La firma HMAC se calcula utilizando el cuerpo original de la solicitud.
- El timestamp forma parte del contenido firmado.
- La ventana temporal de validación es de ±300 segundos.
- La comparación de firmas utiliza `hmac.compare_digest()`.
- La autenticación se realiza antes de publicar los eventos.
- Las etiquetas existentes de S3 se conservan durante las reparaciones.
- Las operaciones de EC2 se verifican antes de confirmar la reparación.
- La validación anti-replay basada en timestamps no mantiene por sí sola un registro de eventos procesados; por lo tanto, no garantiza la detección de duplicados dentro de la ventana permitida.

## 10. Conclusión

La implementación comprende tres áreas principales: seguridad criptográfica, recepción de webhooks y reparación de recursos de infraestructura.

Se incorporaron mecanismos de autenticación mediante HMAC-SHA256, validación temporal, controles de entrada en FastAPI y verificaciones de reparación para instancias EC2 y buckets S3.

Las pruebas específicas registradas finalizaron con 15 resultados satisfactorios, distribuidos entre los tres componentes.

Las capturas incluidas permiten comprobar los resultados obtenidos mediante ejecuciones reales de `pytest` en el entorno del proyecto Fénix.
