# Evidencias de Seguridad, Recepción y Reparación (I3)

## 1. Objetivo

El objetivo es demostrar el funcionamiento de los componentes desarrollados por el Integrante 3 del proyecto Fénix:

- Generación y verificación de firmas HMAC-SHA256.
- Recepción y autenticación de webhooks mediante FastAPI.
- Publicación de eventos autenticados en AWS SQS mediante LocalStack.
- Reparación convergente de recursos EC2 y S3 mediante Boto3.

Las evidencias deben mostrar tanto el escenario nominal como el rechazo de una solicitud cuya firma no es válida.

## 2. Escenario de prueba

Se consideran dos escenarios de reparación y una prueba de autenticación:

1. Generación de la firma HMAC desde el cliente del proyecto.
2. Inicio del receptor HTTP.
3. Preparación de los recursos de demostración.
4. Inducción de un fallo en la instancia EC2 `node-01`.
5. Envío de un evento firmado mediante el webhook.
6. Verificación de la autenticación y publicación del evento en SQS.
7. Procesamiento del evento y reparación de EC2.
8. Envío de una solicitud con firma incorrecta y comprobación del rechazo HTTP 401.
9. Inducción y reparación del escenario S3, si se realiza esa demostración.

## 3. Evidencias del funcionamiento

### 3.1. Generación de firma HMAC

El módulo `src/fenix/utils/crypto.py` implementa la función `signature()`, que genera una firma HMAC-SHA256 a partir de la clave secreta, el timestamp y el cuerpo del mensaje.

La función `verify()` vuelve a calcular la firma esperada y la compara con la recibida mediante `hmac.compare_digest()`.

**Captura requerida:** mostrar el código de `signature()` y `verify()` en el editor.

![Implementación de firma y verificación HMAC](images/10-i3-crypto-hmac.png)

### 3.2. Receptor HTTP activo

Se inició el servidor Uvicorn para exponer el endpoint `POST /webhook`, implementado en `src/fenix/services/receiver.py`.

Este endpoint recibe la cabecera `X-Webhook-Signature`, obtiene el cuerpo original de la solicitud y verifica la firma antes de procesar el contenido.

**Captura requerida:** mostrar la terminal con Uvicorn iniciado y el endpoint disponible.

![Receptor HTTP activo](images/11-i3-receiver-active.png)

### 3.3. Preparación de recursos de demostración

Se ejecutó `setup-demo` para preparar los recursos de laboratorio definidos en el inventario, entre ellos la instancia EC2 `node-01` y el bucket S3 de demostración.

**Captura requerida:** mostrar la ejecución del comando y/o la información de los recursos preparados.

```bash
python -m fenix.cli setup-demo
```

![Preparación de recursos](images/12-i3-demo-resources.png)

### 3.4. Recepción de un webhook válido

Se provocó una falla en la instancia EC2 y se envió el evento mediante el cliente del proyecto.

```bash
python -m fenix.cli fault node-01
python -m fenix.cli send examples/node-event.json
```

El cliente genera la firma y envía el evento al receptor. Si la firma es válida y el cuerpo contiene JSON correcto, el receptor publica el mensaje en SQS y responde con HTTP `202 Accepted`.

**Captura requerida:** mostrar la respuesta HTTP 202 y, si está disponible, el registro de publicación del mensaje en LocalStack.

![Recepción de webhook válido](images/13-i3-webhook-valid.png)

### 3.5. Rechazo de una firma incorrecta

Se envió una solicitud con una firma deliberadamente incorrecta para comprobar que el receptor no acepte mensajes que no superan la autenticación.

```bash
curl -X POST http://127.0.0.1:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Signature: t=1700000000,v1=firma_incorrecta" \
  -d '{"event_id":"test"}'
```

El resultado esperado es HTTP `401 Unauthorized`. La verificación se realiza antes de decodificar el JSON y antes de publicar el mensaje en SQS.

**Captura requerida:** mostrar el comando ejecutado y la respuesta HTTP 401.

![Rechazo de firma incorrecta](images/14-i3-webhook-invalid-signature.png)

### 3.6. Reparación de la instancia EC2

Se ejecutó el worker para consumir el evento enviado a SQS.

```bash
python -m fenix.cli worker
```

La función `repair()` consulta el estado de la instancia EC2 mediante Boto3. Si detecta que `node-01` está detenida, ejecuta `start_instances()` y devuelve el resultado `repaired`.

Si la instancia ya se encuentra en estado `running`, devuelve `already_ok` sin ejecutar una operación de inicio.

**Captura requerida:** mostrar el procesamiento del evento y el resultado `repaired` en la terminal del worker.

![Reparación de instancia EC2](images/15-i3-repair-ec2.png)

### 3.7. Verificación del estado final de EC2

Se verificó el estado de la instancia después de ejecutar la reparación.

El estado esperado para el escenario nominal es `running`.

**Captura requerida:** mostrar la consulta del estado final de `node-01` mediante la herramienta o comando utilizado en el entorno.

![Verificación del estado final de EC2](images/16-i3-verify-ec2.png)

### 3.8. Reparación de etiquetas S3

La función `repair()` también contempla recursos S3. Consulta las etiquetas actuales del bucket y las compara con las etiquetas esperadas.

Si no coinciden, ejecuta `put_bucket_tagging()` para aplicar las etiquetas definidas. Si ya coinciden, devuelve `already_ok`.

**Captura requerida:** mostrar el escenario de etiquetas faltantes, la ejecución de la reparación y el resultado. Esta evidencia debe incluirse solamente si se ejecuta la prueba S3.

![Reparación de etiquetas S3](images/17-i3-repair-s3.png)

### 3.9. Verificación de etiquetas S3

Después de la reparación, se consultaron las etiquetas del bucket para comprobar que coincidan con las esperadas.

**Captura requerida:** mostrar la consulta de etiquetas y su resultado final. Esta evidencia debe incluirse solamente si se ejecuta la prueba S3.

![Verificación de etiquetas S3](images/18-i3-verify-s3.png)

## 4. Resultado

Las evidencias del Integrante 3 deben permitir comprobar que:

- La firma HMAC-SHA256 se genera utilizando la clave secreta, el timestamp y el cuerpo del mensaje.
- El receptor HTTP verifica la firma antes de procesar el evento.
- Una solicitud con firma válida puede ser aceptada y publicada en SQS.
- Una solicitud con firma incorrecta es rechazada mediante HTTP 401.
- La función `repair()` puede iniciar una instancia EC2 detenida.
- La función `repair()` puede restaurar las etiquetas esperadas de un bucket S3.
- La reparación distingue entre un recurso que necesita cambios (`repaired`) y uno que ya está correcto (`already_ok`).

Las pruebas de S3 deben documentarse únicamente si fueron ejecutadas y verificadas. No se debe presentar una captura ilustrativa como si fuera el resultado de una ejecución real.

## 5. Consideraciones técnicas

1. El timestamp forma parte de los datos firmados, pero el receptor no comprueba su antigüedad. Por lo tanto, la implementación no verifica una ventana temporal de validez ni ofrece por sí sola una protección completa contra ataques de repetición (*replay attacks*).
2. `hmac.compare_digest()` se utiliza para comparar la firma esperada con la recibida de forma segura frente a ataques de temporización.
3. El receptor devuelve HTTP `202 Accepted` después de que la publicación en SQS se completa correctamente. Si la publicación falla por una excepción, devuelve HTTP 500.
4. En EC2, los estados transitorios contemplados por `repair()` generan `RetryableError`; los errores considerados permanentes generan `PermanentError`.
5. En S3, la comparación se realiza entre el conjunto completo de etiquetas actuales y el conjunto esperado. Si existen etiquetas adicionales o faltantes, el código aplica el conjunto esperado mediante `put_bucket_tagging()`.
6. Las operaciones de infraestructura se realizan sobre LocalStack en el entorno de demostración, no sobre recursos AWS reales.

## 6. Archivos involucrados

| Archivo | Responsabilidad |
|---|---|
| `src/fenix/utils/crypto.py` | Generación y verificación de firmas HMAC-SHA256. |
| `src/fenix/services/receiver.py` | Recepción HTTP, autenticación del webhook y publicación en SQS. |
| `src/fenix/services/remediation.py` | Función `repair()` para la reparación de recursos EC2 y S3. |
