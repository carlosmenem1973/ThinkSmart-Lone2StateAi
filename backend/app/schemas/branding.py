from pydantic import BaseModel, Field, field_validator

class BrandingUpdate(BaseModel):
    product_name: str = Field(min_length=2, max_length=100)
    customer_name: str = Field(min_length=2, max_length=160)
    tagline: str = Field(default="Real Estate Intelligence", max_length=240)
    logo_url: str | None = Field(default=None, max_length=1000)
    primary_color: str = Field(default="#2563EB", pattern=r"^#[0-9A-Fa-f]{6}$")
    accent_color: str = Field(default="#16866C", pattern=r"^#[0-9A-Fa-f]{6}$")

    @field_validator("logo_url")
    @classmethod
    def validate_logo_url(cls, value):
        if value and not (value.startswith("https://") or (value.startswith("/") and not value.startswith("//"))):
            raise ValueError("Logo URL must use HTTPS or a site-relative path (not a protocol-relative URL)")
        return value
