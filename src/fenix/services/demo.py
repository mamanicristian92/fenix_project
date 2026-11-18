"""Laboratorio acotado de recursos. Integrante 2 prepara, integrante 6 verifica."""
import time
from fenix.config.settings import client
from fenix.utils.state import load, save
from fenix.utils.validation import identifier
from fenix.utils.errors import ValidationError, RetryableError
from botocore.exceptions import ClientError  # Distingue códigos de error concretos.
from fenix.services.cloud_support import aws_tags, mock_inputs, create_instance, create_group

INVENTORY_PATH = "data/inventory.json"

def _bucket_tags(s3, name: str) -> dict[str, str]:
    """Lee las etiquetas de un bucket tratando solo NoSuchTagSet como vacías.

    Args:
        s3: Cliente S3 ya construido.
        name: Nombre del bucket consultado.
    Returns:
        Mapa clave -> valor de las etiquetas actuales; {} solo sin etiquetas.
    Raises:
        ClientError: Cualquier otro fallo del SDK se propaga sin ocultarlo.
    """
    try:
        return {row["Key"]: row["Value"]
                for row in s3.get_bucket_tagging(Bucket=name)["TagSet"]}
    except ClientError as error:  # Solo la ausencia total equivale a tags vacías.
        code = error.response.get("Error", {}).get("Code", "")
        if code != "NoSuchTagSet":
            raise  # Un 403 o un bucket ajeno no son "sin etiquetas".
        return {}
    
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
    
    group = identifier(group)
    
    inventory = load(INVENTORY_PATH)
    node = inventory.setdefault("node-01", {})
    
    project_tag = "fenix"
    base = {"ManagedBy": "ppa2", "Project": project_tag, "GroupId": group ,"Owner": group}
    ec2 = client("ec2")
    vpc_id , image_id = mock_inputs()
    sg_name = f"fenix-{group}-sg" 
    
    groups_response = ec2.describe_security_groups(Filters=[
        {"Name": "tag:ManagedBy", "Values": ["ppa2"]},
        {"Name": "tag:Project", "Values": [project_tag]},
        {"Name": "tag:GroupId", "Values": [group]},
        {"Name": "tag:Owner", "Values": [group]},
        {"Name": "group-name", "Values": [sg_name]},
    ])
    
    groups = groups_response["SecurityGroups"]
    
    if groups:
        sg_id = groups[0]["GroupId"]
    else:
        sg_id = create_group(sg_name, vpc_id, base)
        
    token = f"fenix-{group}-node-01"
    node_tags = {**base, "Name": "node-01"}
    node.update({"security_group_id": sg_id, "image_id": image_id, "client_token": token, "expected_tags": dict(node_tags)})
    save(INVENTORY_PATH, inventory)
    
    states = ["pending", "running", "stopping", "stopped"]
    
    reservations_response = ec2.describe_instances(Filters=[
        {"Name": "tag:ManagedBy", "Values": ["ppa2"]},
        {"Name": "tag:Project", "Values": [project_tag]},
        {"Name": "tag:GroupId", "Values": [group]},
        {"Name": "tag:Owner", "Values": [group]},
        {"Name": "tag:Name", "Values": ["node-01"]},
        {"Name": "instance.group-id", "Values": [sg_id]},
        {"Name": "instance-state-name", "Values": states},
    ])
    
    reservations = reservations_response["Reservations"]   
    
    ids = []
    
    for reservation in reservations:
        instances = reservation["Instances"]
        for instance in instances:
            ids.append(instance["InstanceId"])
    
    if ids:
        instance_id = ids[0]
    else:
        instance_id = create_instance(image_id, sg_id, token, dict(node_tags))
    
    node.update({"id": instance_id, "type": "ec2"})
    save(INVENTORY_PATH, inventory)
       
    detail_response = ec2.describe_instances(InstanceIds=[instance_id])
    detail = detail_response["Reservations"]
    
    if not detail:
        raise ValidationError("No se pudo verificar la instancia creada")  
    
    name = f"fenix-{group}-demo"
    s3 = client("s3")
    
    known = []
    buckets = s3.list_buckets().get("Buckets", [])

    for bucket in buckets:
        known.append(bucket["Name"])

    if name in known:
        current = _bucket_tags(s3, name)
    else:
        # Guardo el bucket antes de ponerle las etiquetas.
        s3.create_bucket(Bucket=name)
        inventory["bucket-01"] = {"id": name,"type": "s3","expected_tags": dict(base)}
        save(INVENTORY_PATH, inventory)
        current = {}

    for key, value in base.items():
        if key in current and current[key] != value:
            raise ValidationError(f"Tag {key} conflict: {current[key]} vs {value}")

    merged_tags = dict(current)
    for key, value in base.items():
        merged_tags[key] = value

    if merged_tags != current:
        s3.put_bucket_tagging(Bucket=name, Tagging={"TagSet": aws_tags(merged_tags)})

    verified_tags = _bucket_tags(s3, name)
    for key, value in base.items():
        if verified_tags.get(key) != value:
            raise RetryableError("No se pudieron verificar las etiquetas del bucket")

    inventory["bucket-01"] = {"id": name,"type": "s3","expected_tags": dict(base)}
    save(INVENTORY_PATH, inventory)

    return inventory
    

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
