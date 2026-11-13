# Proyecto Fenix

Sistema de simulación de autorreparación de infraestructura que detecta eventos, los procesa de forma asíncrona y ejecuta acciones de recuperación sobre recursos simulados, con mecanismos de reintento, trazabilidad y notificación.

### Descripción general

Fénix implementa un flujo automatizado de respuesta ante fallos de infraestructura. Cuando recibe un evento mediante un webhook, valida su autenticidad y estructura, lo publica en una cola de mensajes y permite que un worker lo procese de manera independiente.

Según el tipo de evento recibido, el sistema ejecuta una acción de reparación sobre los recursos simulados y notifica el resultado. Si ocurre un error durante el procesamiento, el mensaje puede volver a intentarse y, al superar el límite configurado, enviarse a una cola de mensajes fallidos (*Dead Letter Queue*, DLQ).

El objetivo es demostrar cómo distintos componentes pueden colaborar para implementar un mecanismo de recuperación automatizada, sin depender de infraestructura cloud real.

### Características principales

- **Recepción de eventos:** endpoint HTTP para recibir notificaciones mediante webhooks.
- **Autenticación:** verificación de firmas HMAC para validar la autenticidad de los eventos.
- **Validación:** comprobación de la estructura y los datos recibidos.
- **Procesamiento asíncrono:** publicación y consumo de mensajes mediante Amazon SQS simulado con LocalStack.
- **Autorreparación:** ejecución de acciones sobre recursos simulados de EC2 y S3.
- **Reintentos y DLQ:** tratamiento de fallos de procesamiento y derivación de mensajes que agotan sus reintentos.
- **Idempotencia y seguimiento:** conservación del progreso para evitar repetir innecesariamente acciones ya completadas.
- **Notificaciones:** comunicación del resultado de las operaciones mediante proveedores externos.
- **Observabilidad:** registros estructurados en formato JSON, procesamiento asíncrono de logs y rotación con compresión gzip.

## Tecnologías utilizadas

| Tecnología | Propósito |
|---|---|
| Python | Lenguaje principal del proyecto |
| FastAPI | Exposición del endpoint HTTP para recepción de webhooks |
| Amazon SQS | Sistema de mensajería para procesamiento asíncrono |
| LocalStack | Simulación local de servicios de AWS |
| Boto3 | Comunicación con los servicios de AWS simulados |
| HMAC | Autenticación e integridad de los webhooks |
| Logging de Python | Registro de eventos y observabilidad |
| JSON | Formato de intercambio y almacenamiento de registros |
| Gzip | Compresión de archivos históricos de logs |
| Pytest | Ejecución de pruebas automatizadas |

### Recursos simulados

Fénix no realiza operaciones sobre infraestructura AWS real. Los recursos se representan mediante objetos y servicios simulados para permitir la ejecución y validación del flujo de autorreparación en un entorno controlado.

Los escenarios principales contemplan:

- **EC2:** recuperación de una instancia identificada como `node-01`.
- **S3:** reparación de las etiquetas (*tags*) de un bucket identificado como `bucket-01`.

LocalStack proporciona el entorno local para los servicios de mensajería, evitando la necesidad de utilizar una cuenta de AWS o incurrir en costos de infraestructura cloud.

### Requisitos

- Python 3.11 o superior
- Docker Compose

## Instalación

1.  Clonar el repositorio

    1. Ve a la carpeta donde quieres guardar el proyecto:
        
        ```bash
        cd ruta/de/la/carpeta
        ```

    2. Clona el repositorio:
        
        ```bash
        git clone git@github.com:mamanicristian92/fenix_project.git
        ```

        *Nota: el comando utiliza SSH. Asegurate de tener configurada una clave SSH en GitHub.*

    3. Entra al proyecto:
        
        ```bash
        cd vulcano_engine
        ```

2. Entorno virtual:
    
    1. Crear el entorno (dentro de la carpeta del proyecto):
        
        - Windows (CMD / Powershell):

            ```bash
            python -m venv .venv
            ```
        
        - Linux / macOS:

            ```bash
            python3 -m venv .venv
            ```
        
        *Esto crea una carpeta llamada `.venv`*
    
    2. Activar el entorno virtual

        - Windows (CMD):

            ```bash
            .venv\Scripts\activate
            ```

        - Windows (PowerShell):

            ```bash
            .\.venv\Scripts\Activate.ps1
            ```

        - Linux / macOS:
            
            ```bash
            source .venv/bin/activate
            ```
        
        *Nota: Cuando esté activado, normalmente verás algo como `(.venv)`*

3. Instalar dependencias y el paquete fenix:
    
    - Con el entorno activado:

        ```bash
        python -m pip install -r requirements.txt
        ```

    - Instalar el paquete como editable:

        ```bash
        python -m pip install -e .
        ```

4. Configurar el archivo .env

    Copiá el archivo de configuración de ejemplo:

    - Windows (CMD):

        ```bash
        copy .env.example .env
        ```

    - Linux / macOS /Powershell:

        ```bash
        cp .env.example .env
        ```

    - Pon tus claves en el .env

        ```
        AWS_ACCESS_KEY_ID=
        AWS_SECRET_ACCESS_KEY=
        WEBHOOK_SECRET=
        LOCALSTACK_AUTH_TOKEN=
        TELEGRAM_BOT_TOKEN=
        ```
    
    - Nota:

      - LOCALSTACK_AUTH_TOKEN: consigue tu token en [localstack.cloud](https://www.localstack.cloud/)
      - TELEGRAM_BOT_TOKEN: consigue el token con BotFather de Telegram
      - Para más información consultar [CONTRIBUTING.md](CONTRIBUTING.md)

## Cómo Usar

1. Levantar Localstack

    - Desde la carpeta del proyecto:

        ```bash
        docker compose up
        ```

        Nota: Esto crea y levanta localstack.

2. Iniciar la Cola de eventos, la DLQ y agregar la política de reintentos:

    - En otra terminal (con el **entorno activado** y en la carpeta raíz):

        ```bash
        python -m fenix.cli init-queues
        ```

3. Iniciar el receptor de webhooks HTPP

    - En otra terminal (con el **entorno activado** y en la carpeta raíz):

        ```bash
        python -m uvicorn fenix.services.receiver:app --host 127.0.0.1 --port 8000 --workers 1 --env-file .env
        ```

4. Preparar y ejecutar un escenario demostrativo:

    - En otra terminal (con el **entorno activado** y en la carpeta raíz):

        ```bash
        python -m fenix.cli demo
        ```

#### Anatomía:

|Argument     |Description                          |
|-------------|-------------------------------------|
|init-queues  |Prepara work y DLQ.                      |
|setup-demo   |Crea el laboratorio autorizado.          |
|send         |Emite el evento por HTTP.                |
|fault        |Introduce una falla controlada.          |

---

### Calidad y pruebas

El proyecto cuenta con pruebas automatizadas y herramientas de análisis estático
(Flake8 y Pylint) para verificar su correcto funcionamiento y mantener la
calidad del código.

Para conocer cómo ejecutar las pruebas y las herramientas de análisis, consultar [CONTRIBUTING.md](CONTRIBUTING.md).

---

###  Diagrama de Arquitectura de Telemetría


---

## Contribuciones

### Equipo 404

| **Ruta** | **Función** | **Autor principal** |
| --- | --- | --- |
| **`src/fenix/config/settings.py`** | Clientes Boto3 y protección del endpoint | Apoyo entregado y revisión de I2 |
| **`src/fenix/utils/errors.py y validation.py`** | Excepciones, identificadores y fechas UTC | I1 |
| **`src/fenix/services/events.py`** | Validación del esquema y del inventario | I1 |
| **`src/fenix/services/sqs.py y demo.py`** | Colas, DLQ y laboratorio EC2/S3 | I2 |
| **`src/fenix/utils/crypto.py y services/receiver.py`** | HMAC y receptor HTTP | I3 |
| **`src/fenix/services/remediation.py función repair`** | Reparación convergente EC2/S3 | I3 |
| **`src/fenix/utils/logging_json.py y services/notifications.py`** | Logs, gzip y proveedor externo | I4 |
| **`src/fenix/services/worker.py y remediation.handle`** | Consumo y registro por etapas | I5 |
| **`src/fenix/cli.py`** | Interfaz y manejo de ciclo de vida | I5 |
| **`tests/ y demo.inject_fault`** | Pruebas, fallas y evidencias | I6 o reparto para cinco |
| **`src/fenix/utils/state.py`** | Lectura y escritura atómica del ledger | Apoyo entregado |

| Rol | Apellido, Nombre (Github) | Correo |
|---|---|---|
| I1 |[Lescano, Jessica Daiana](https://www.github.com/daylagitana89jl-oss) | daylagitana89.jl@gmail.com |
| I2 |[Venticola, Leandro Enrique](https://github.com/leoventicola/) | venticolaleandro@gmail.com |
| I3 |[Cointte Cedron, Mateo](https://github.com/Th-30Mateo) | cointtemateo20@gmail.com |
| I4 |[Choque, Ismael Alejandro](https://www.github.com/ismahack7) | ismaelchoque021@gmail.com |
| I5 |[Martinez, Gustavo Alejandro](https://www.github.com/gusmz111) | gustavom111@hotmail.com |
| I6 |[Mamaní, Cristian Alfredo](https://www.github.com/mamanicristian92) | mamanicristian92@gmail.com |

### Video de presentación

