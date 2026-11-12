# fenix\_project

\## Notificaciones de Telegram



FENIX permite enviar notificaciones mediante un bot de Telegram.



\### 1. Crear el bot



\- Abrir Telegram y buscar `@BotFather`.

\- Ejecutar `/newbot`.

\- Elegir el nombre y el username del bot.

\- Guardar el token generado de forma segura.

\- Abrir el bot creado y presionar Iniciar (`/start`).



\### 2. Configurar las credenciales



Crear el archivo local `.env` a partir del ejemplo:



```bash

cp .env.example .env

```



Completar estas variables en `.env`:



```dotenv

TELEGRAM\_BOT\_TOKEN=tu\_token

TELEGRAM\_CHAT\_ID=tu\_chat\_id

```



El `chat\_id` se puede consultar enviando un mensaje al bot y utilizando el método `getUpdates` de la API de Telegram.



\*\*Seguridad:\*\* nunca subir el archivo `.env` a GitHub ni compartir el token del bot. El repositorio incluye `.env.example` sin credenciales reales.



\### 3. Probar el envío



Con las dependencias instaladas y desde la raíz del proyecto, ejecutar:



```bash

PYTHONPATH=src python -c "from dotenv import load\_dotenv; load\_dotenv(); from fenix.services.notifications import notify; notify('FENIX: prueba de conexión con Telegram')"

```



Si la configuración es correcta, el mensaje llegará a la conversación privada con el bot.



\### 4. Manejo de errores



El proveedor contempla errores de conexión, límites de solicitudes HTTP 429, errores temporales HTTP 5xx y rechazos permanentes. Los registros no deben exponer el token ni la URL privada que lo contiene.
