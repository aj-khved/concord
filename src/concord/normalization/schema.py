from pydantic import BaseModel


class CanonicalVendorRecord(BaseModel):
    source: str
    source_record_id: str
    legal_name: str
    address_line1: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    country: str | None = None
    tax_id: str | None = None
    phone: str | None = None
    category: str | None = None
