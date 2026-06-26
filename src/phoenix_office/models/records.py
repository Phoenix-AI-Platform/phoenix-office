"""Customer and job record data models."""

from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    """The current status of a job."""

    draft = "draft"
    proposed = "proposed"
    accepted = "accepted"
    scheduled = "scheduled"
    completed = "completed"
    cancelled = "cancelled"


class TankLocationType(StrEnum):
    """The physical location of the tank on the property."""

    aboveground = "aboveground"
    underground = "underground"
    basement = "basement"
    unknown = "unknown"


class CustomerRecord(BaseModel):
    """A customer record representing a person or organization."""

    customer_id: str = Field(..., min_length=1, description="Unique identifier for the customer.")
    display_name: str = Field(
        ..., min_length=1, description="Full name or company name for display."
    )
    phone: str | None = Field(default=None, description="Primary contact phone number.")
    email: str | None = Field(default=None, description="Primary contact email address.")
    billing_street_address: str | None = Field(
        default=None, description="Street address for billing."
    )
    billing_city_state_zip: str | None = Field(
        default=None, description="City, state, and ZIP for billing."
    )
    notes: list[str] = Field(
        default_factory=list, description="General notes about the customer."
    )


class JobRecord(BaseModel):
    """A job record representing a project or service call for a customer."""

    job_id: str = Field(..., min_length=1, description="Unique identifier for the job.")
    customer_id: str = Field(
        ..., min_length=1, description="ID of the customer this job belongs to."
    )
    job_name: str = Field(..., min_length=1, description="Short descriptive name for the job.")
    site_street_address: str = Field(
        ..., min_length=1, description="Street address of the job site."
    )
    site_city_state_zip: str = Field(
        ..., min_length=1, description="City, state, and ZIP of the job site."
    )
    status: JobStatus = Field(
        default=JobStatus.draft, description="Current progress status of the job."
    )
    tank_location_type: TankLocationType = Field(
        default=TankLocationType.unknown, description="Where the tank is located."
    )
    tank_size_gallons: int | None = Field(
        default=None, gt=0, description="Capacity of the tank in gallons, if known."
    )
    tank_contents: str | None = Field(
        default=None, description="Description of the tank's contents, if known."
    )
    contents_known: bool = Field(
        default=False, description="Whether the exact contents of the tank are known."
    )
    scope_notes: list[str] = Field(
        default_factory=list, description="Notes specific to the scope of work."
    )
    internal_notes: list[str] = Field(
        default_factory=list, description="Internal notes not shared with the customer."
    )
