"Stable artifact errors with machine-addressable JSON paths."

from __future__ import annotations


class ArtifactContractError(ValueError):
    "Base error with a stable artifact and JSON-path location."

    kind: str = "contract"

    def __init__(self, artifact: str, path: str, message: str) -> None:
        self.artifact: str = artifact
        self.path: str = path or "$"
        self.detail: str = message
        super().__init__(f"{artifact} {self.path}: {message}")


class ArtifactSyntaxError(ArtifactContractError):
    kind: str = "syntax"


class ArtifactSchemaError(ArtifactContractError):
    kind: str = "schema"


class ArtifactDomainError(ArtifactContractError):
    kind: str = "domain"
