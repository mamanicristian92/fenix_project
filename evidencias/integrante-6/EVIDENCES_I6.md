## Evidencias Reproducibles del integrante 6

## Apoyos entregados

- ### Test Base (Prueba el apoyo entregado)
    `python -m pytest -v tests/test_base.py`

![01_test_base.png](images/01_test_base.png)

- ### Test Contracts (Evalúa el cumplimiento de contratos en validation.py)
    `python -m pytest -v tests/test_contracts.py`

![02_test_contracts.png](images/02_test_contracts.png)

## Tests implementados por i6

- ### Test Fenix
    Tests cubiertos de la Matriz de Pruebas
    - F04	Firma ausente/alterada y timestamp de hace una hora	401 y ningún mensaje nuevo
    - F05	Mismos datos JSON con bytes distintos tras firmar	401 por HMAC inválida
    - F06	JSON roto firmado; luego lista JSON firmada	400 y 422 respectivamente; sin publicación
    - F07	Alias ajeno y claves extra	Rechazo de esquema; ningún cambio cloud
    - F09	simulate_failures=2, ID nuevo	Backoff 2 y 4; después reparación y ACK

    `python -m pytest -v --tb=short tests/test_fenix.py`

![03_test_fenix.png](images/03_test_fenix.png)
![04_test_fenix_summary.png](images/04_test_fenix_summary.png)

- ### Test Scenarios
    `python -m pytest -v --tb=short tests/test_scenarios.py`

![05_test_scenarios.png](images/05_test_scenarios.png)

## Prueba de ejecución: Una falla llega efectivamente a DLQ

En la siguiente prueba de integración:
- Enviaremos un evento que no cumpla el contrato.
- El webhook lo encolará al SQS
- El worker reintentará validarlo 3 veces y luego SQS lo envía a la DLQ

### Con el proyecto levantado y el worker en ejecución

### 1. Usamos un script auxiliar con boto3 para ver el tamaño de la DLQ
`python scripts/check_dlq.py`

![06_check_dlq_first_time.png](images/06_check_dlq_first_time.png)

### 2. Evento que incumple validación
![07_failed_event_node.png](images/07_failed_event_node.png)

### 3. Enviamos el evento
`python -m fenix.cli send examples/node-event.json`

![08_cli_send_node_event.png](images/08_cli_send_node_event.png)

### 4. Volvemos a chequear el tamaño de la DLQ
`python scripts/check_dlq.py`

![09_check_dlq_second_time.png](images/09_check_dlq_second_time.png)

Nota: Efectivamente el tamaño de la DQL se ve incrementado

### 5. Revisamos Logs del Worker (Analizamos comportamiento)

Podemos observar que el worker levantó los ValidationError en cada lectura y ejecutó el backoff, aunque no muestre la derivación del evento a la DLQ.
![10_worker_logs.png](images/10_worker_logs.png)