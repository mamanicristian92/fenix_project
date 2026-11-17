"""Laboratorio acotado de recursos. Integrante 2 prepara, integrante 6 verifica."""
import time
from fenix.config.settings import client
from fenix.utils.state import load, save
from fenix.utils.validation import identifier
from botocore.exceptions import ClientError
from fenix.utils.errors import ValidationError, RetryableError


def setup_demo(group: str) -> dict:
    """Prepara una instancia mock y un bucket a partir de identificadores estables.

    Args:
        group: ID validado del grupo; determina prefijos de los recursos.
    Returns:
        Inventario con aliases node-01 y bucket-01 y sus IDs reales del emulador.
    Raises:
        ClientError: Si el emulador no soporta una operación o falla su ejecución.
        NotImplementedError: Mientras falte TODO I2-C.
    Side Effects:
        Crea recursos de laboratorio etiquetados y data/inventory.json.
    Notes:
        Reutilizar por tags antes de crear y guardar IDs después de cada creación.
        Obtener una ImageId con describe_images; no copiar una AMI de AWS real.
    """
    # TODO I2-C: validar group; localizar VPC predeterminada mediante describe_vpcs.
    # Crear/reusar SG fenix-{group}-sg con tag ManagedBy=ppa2 y GroupId=group.
    # Usar describe_images y registrar la ImageId mock elegida en inventory.json.
    # Crear/reusar instancia por tags Project=fenix/GroupId/Name; ClientToken estable.
    # run_instances: MinCount=MaxCount=1, tipo t3.micro y SecurityGroupIds=[sg_id].
    # Crear/reusar bucket fenix-{group}-demo; región us-east-1 para este laboratorio.
    # Aplicar tags ManagedBy=ppa2, Project=fenix, GroupId=group y Owner=group.
    # Publicar inventario solo con recursos cuya propiedad haya sido verificada.
    raise NotImplementedError("I2-C: crear laboratorio e inventario")


def inject_fault(alias: str) -> None:
    """Detiene el nodo o elimina una etiqueta del bucket de laboratorio.

    Args:
        alias: node-01 o bucket-01 presente en inventory.json.
    Returns:
        None cuando el fallo simulado se verifica mediante el SDK.
    Raises:
        ValidationError: Si el alias no pertenece al inventario.
        RetryableError: Si el estado esperado no se alcanza.
    """
    # TODO I6-A: resolver el alias en inventario; jamás recibir InstanceId libre.
    # node-01: stop_instances y comprobar stopped, con consultas limitadas.
    # bucket-01: quitar Owner conservando el resto de etiquetas.
    # Esta función fabrica el problema; no debe enviar el evento automáticamente.

    aliases = ("node-01", "bucket-01")

    if alias not in aliases:
        raise ValidationError("Alias de recurso no permitido")
    
    inventory = load("data/inventory.json")
    if alias not in inventory:
        raise ValidationError("El recurso no existe en el inventario")
    
    resource = inventory[alias]
    if not isinstance(resource, dict) or not resource.get("id"):
        raise ValidationError("Registro de recurso inválido")
    
    if alias == "node-01":
        ec2 = client("ec2")
        instance_id = resource["id"]
        def get_state():
            response = ec2.describe_instances(
                InstanceIds=[instance_id]
            )
            instances = [
                instance
                for reservation in response["Reservations"]
                for instance in reservation["Instances"]
            ]
            if len(instances) != 1:
                raise ValidationError("No se pudo identificar la instancia")

            return instances[0]["State"]["Name"]
        
        state = get_state()
        if state == "running":
            ec2.stop_instances(InstanceIds=[instance_id])
        elif state not in ("stopping", "pending", "stopped"):
            raise ValidationError(
                f"Estado de instancia no permitido: {state}"
            )

        for attempt in range(5):
            if get_state() == "stopped":
                return None
            if attempt < 4:
                time.sleep(1)
        raise RetryableError(
            "La instancia no alcanzó el estado stopped"
        )

    if alias == "bucket-01":
        s3 = client("s3")
        bucket_name = resource["id"]

        try:
            response = s3.get_bucket_tagging(Bucket=bucket_name)
            tags = response["TagSet"]
        except ClientError as error:
            if error.response["Error"]["Code"] == "NoSuchTagSet":
                return None
            raise

        remaining_tags = [
            tag for tag in tags if tag["Key"] != "Owner"
        ]

        # Si Owner ya no existe, la falla ya está presente.
        if len(remaining_tags) == len(tags):
            return None

        if remaining_tags:
            s3.put_bucket_tagging(
                Bucket=bucket_name,
                Tagging={"TagSet": remaining_tags}
            )
        else:
            s3.delete_bucket_tagging(Bucket=bucket_name)

        # Verificar que Owner realmente haya desaparecido.
        try:
            verification = s3.get_bucket_tagging(Bucket=bucket_name)
            final_tags = verification["TagSet"]
        except ClientError as error:
            if error.response["Error"]["Code"] == "NoSuchTagSet":
                final_tags = []
            else:
                raise

        if any(tag["Key"] == "Owner" for tag in final_tags):
            raise RetryableError(
                "No se pudo eliminar la etiqueta Owner"
            )

        return None
