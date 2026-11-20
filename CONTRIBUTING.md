# Configuraciones para el desarrolador.

### Índice

- [Cómo configurar el BOT de Telegram y](#notificaciones-de-telegram)
- [Como Ejecutar los Tests](#como-ejecutar-los-tests)

## Notificaciones de Telegram

FENIX permite enviar notificaciones mediante un bot de Telegram.

### 1. Crear el bot

- Abrir Telegram y buscar `@BotFather`.
- Ejecutar `/newbot`.
- Elegir el nombre y el username del bot.
- Guardar el token generado de forma segura.
- Abrir el bot creado y presionar Iniciar (`/start`).

### 2. Configurar las credenciales

Completar estas variables en `.env`:

```dotenv
NOTIFY_PROVIDER=telegram
TELEGRAM_BOT_TOKEN=tu_token
TELEGRAM_CHAT_ID=tu_chat_id
```

El `chat_id` se puede consultar enviando un mensaje al bot y utilizando el método `getUpdates` de la API de Telegram.

### 3. Probar el envío

Con las dependencias instaladas y desde la raíz del proyecto, ejecutar:

```bash
python -c "from dotenv import load_dotenv; load_dotenv(); from fenix.services.notifications import notify; notify('FENIX: prueba de conexión con Telegram')"
```

Si la configuración es correcta, el mensaje llegará a la conversación privada con el bot.

### 4. Manejo de errores

El proveedor contempla errores de conexión, límites de solicitudes HTTP 429, errores temporales HTTP 5xx y rechazos permanentes. Los registros no deben exponer el token ni la URL privada que lo contiene.


## Como Ejecutar los tests

### Apoyos entregados

- ### Test Base (Prueba el apoyo entregado)
    python -m pytest -v tests/test_base.py


- ### Test Contracts (Evalúa el cumplimiento de contratos en validation.py)
    python -m pytest -v tests/test_contracts.py


### Tests implementados por i6

- ### Test Fenix
    Tests cubiertos de la Matriz de Pruebas
    - F04	Firma ausente/alterada y timestamp de hace una hora	401 y ningún mensaje nuevo
    - F05	Mismos datos JSON con bytes distintos tras firmar	401 por HMAC inválida
    - F06	JSON roto firmado; luego lista JSON firmada	400 y 422 respectivamente; sin publicación
    - F07	Alias ajeno y claves extra	Rechazo de esquema; ningún cambio cloud
    - F09	simulate_failures=2, ID nuevo	Backoff 2 y 4; después reparación y ACK

    python -m pytest -v tests/test_fenix.py

- ### Test Scenarios
    python -m pytest -v tests/test_scenarios.py