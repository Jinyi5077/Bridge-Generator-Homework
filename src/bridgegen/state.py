"""Immutable calculation records assembled before document export."""
from dataclasses import asdict, dataclass
from types import MappingProxyType
from copy import deepcopy


@dataclass(frozen=True)
class LoadCase:
    id: str
    name: str
    category: str
    value: float
    unit: str
    stage: str
    source: str
    description: str


@dataclass(frozen=True)
class CombinationDefinition:
    id: str
    name: str
    gamma_g_options: tuple
    gamma_q: float
    vehicle_factor: float
    include_impact: bool
    apply_importance_factor: bool
    source: str


@dataclass(frozen=True)
class CalculationRecord:
    id: str
    category: str
    purpose: str
    formula: str
    inputs: dict
    result: float | str
    unit: str
    source: str


@dataclass(frozen=True)
class DesignState:
    version: str
    status_code: str
    payload: MappingProxyType

    @classmethod
    def freeze(cls, version, status_code, payload):
        return cls(version, status_code, MappingProxyType(deepcopy(payload)))

    def to_dict(self):
        data = deepcopy(dict(self.payload))
        data["version"] = self.version
        data["status_code"] = self.status_code
        return data


def records_to_dict(items):
    return [asdict(item) for item in items]

