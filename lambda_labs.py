from typing import Any, Optional, List, Dict, NewType
from dataclasses import dataclass
from dataclasses_json import DataClassJsonMixin

import requests


def load_api_key(filename: str = "./lambda_api_key.txt") -> str:
    with open(filename, "r") as f:
        return f.read().strip()


InstanceID = NewType("InstanceID", str)
RegionName = NewType("RegionName", str)
InstanceTypeName = NewType("InstanceTypeName", str)
InstanceStatus = NewType("InstanceStatus", str)


@dataclass
class InstanceSpecs(DataClassJsonMixin):
    memory_gib: int
    storage_gib: int
    vcpus: int


@dataclass
class InstanceType(DataClassJsonMixin):
    name: InstanceTypeName
    description: str
    price_cents_per_hour: int
    specs: InstanceSpecs


@dataclass
class RegionWithDescription(DataClassJsonMixin):
    name: RegionName
    description: str


@dataclass
class OfferedInstanceType(DataClassJsonMixin):
    instance_type: InstanceType
    regions_with_capacity_available: List[RegionWithDescription]


STATUS_ACTIVE = "active"
STATUS_BOOTING = "booting"
STATUS_UNHEALTHY = "unhealthy"
STATUS_TERMINATED = "terminated"


@dataclass
class InstanceDetails(DataClassJsonMixin):
    id: InstanceID
    name: str
    status: InstanceStatus
    region: RegionWithDescription
    ssh_key_names: List[str]
    file_system_names: List[str]
    instance_type: InstanceType
    hostname: Optional[str] = None
    ip: Optional[str] = None
    jupyter_token: Optional[str] = None
    jupyter_url: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.status == STATUS_ACTIVE

    @property
    def is_terminated(self) -> bool:
        return self.status == STATUS_TERMINATED

@dataclass
class SSHKey(DataClassJsonMixin):
    id: str
    name: str
    public_key: str
    private_key: Optional[str] = None


@dataclass
class LaunchInstanceRequest(DataClassJsonMixin):
    name: str
    region_name: str
    instance_type_name: str
    ssh_key_names: List[str]
    file_system_names: List[str]
    quantity: int = 1


class LambdaAPIError(Exception):
    pass


class LambdaAPI:
    api_key: str
    base_uri: str = "https://cloud.lambdalabs.com/api/v1/"

    instances_url: str = "https://cloud.lambdalabs.com/instances"

    def __init__(self, api_key: Optional[str] = None):
        if api_key is None:
            api_key = load_api_key()
        self.api_key = api_key

    @property
    def headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def get_offered_instance_types(self) -> List[OfferedInstanceType]:
        instance_types = self._get("instance-types", {})
        return [
            OfferedInstanceType.from_dict(value) for value in instance_types.values()
        ]

    def get_instances(self) -> List[InstanceDetails]:
        instances = self._get("instances", [])
        return [InstanceDetails.from_dict(instance) for instance in instances]

    def get_instance_details(self, id: InstanceID) -> InstanceDetails:
        details = self._get(f"instances/{id}")
        if details is None:
            raise LambdaAPIError(f"Instance {id} not found")
        return InstanceDetails.from_dict(details)

    def launch_instance(
        self,
        name: str,
        instance_type_name: InstanceTypeName,
        region_name: RegionName,
        ssh_keys: List[SSHKey],
    ) -> InstanceID:
        request = LaunchInstanceRequest(
            name=name,
            instance_type_name=instance_type_name,
            region_name=region_name,
            ssh_key_names=[key.name for key in ssh_keys],
            file_system_names=[],
            quantity=1,
        )
        response = self._post("instance-operations/launch", request.to_dict())
        if response is None:
            raise LambdaAPIError("Failed to launch instance")

        instance_ids = response.get("instance_ids", [])

        if len(instance_ids) == 0:
            raise LambdaAPIError(f"Failed to launch instance {name}")

        if len(instance_ids) > 1:
            raise LambdaAPIError(f"Expected only one instance id, got {instance_ids}")

        return InstanceID(instance_ids[0])

    def get_ssh_keys(self) -> List[SSHKey]:
        return [SSHKey.from_dict(key) for key in self._get("ssh-keys", [])]

    def terminate_instances(self, instance_ids: List[str]) -> None:
        response = requests.post(
            self.base_uri + "instance-operations/terminate",
            json={"instance_ids": instance_ids},
            headers=self.headers,
        )
        print(response.json())

    def terminate_all_instances(self) -> None:
        instances = self.get_instances()
        instance_ids = [instance["id"] for instance in instances]
        self.terminate_instances(instance_ids)

    def _get(self, path: str, default: Any = None) -> Any:
        response = requests.get(self.base_uri + path, headers=self.headers)
        return response.json().get("data", default)

    def _post(self, path: str, data: Any, default: Any = None) -> Any:
        response = requests.post(self.base_uri + path, json=data, headers=self.headers)
        if response.status_code != 200:
            raise LambdaAPIError(f"Failed to create instance: {response.status_code} {response.text}")
        return response.json().get("data", default)
