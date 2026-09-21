from pydantic import BaseModel


class MedicationCatalogEntryOut(BaseModel):
    id: str
    name: str
    dosage: str
    unit: str
    form: str
    type: str


class CatalogSearchResponse(BaseModel):
    entries: list[MedicationCatalogEntryOut]
    next_cursor: str | None


class CatalogMetadataResponse(BaseModel):
    types: list[str]
    dosage_units: list[str]
