"""Pydantic schemas: PetCreate, PetUpdate, PetOut. (Phase 3)

The API shape, not the table shape. The bounds here deliberately mirror the
column widths and the check constraint in models/pet.py, so a bad value is a
422 from pydantic rather than a 500 from the database driver.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models import Sex


class _PetBase(BaseModel):
    """Fields shared by create and update, with the column limits restated.

    extra="forbid" for the same reason it is on _Credentials: a silently dropped
    key is how "owner_id": 7 in a PATCH body becomes a bug report instead of a
    422.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=80)
    species: str | None = Field(default=None, min_length=1, max_length=40)
    breed: str | None = Field(default=None, max_length=80)
    sex: Sex | None = None
    date_of_birth: date | None = None
    # ge=0 mirrors ck_pets_weight_non_negative. Without it the constraint still
    # holds, but the client gets an IntegrityError-shaped 500 instead of a 422.
    weight_kg: float | None = Field(default=None, ge=0)
    # The column is Text, i.e. unbounded. A cap keeps a single request from
    # writing a megabyte of notes.
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("date_of_birth")
    @classmethod
    def _not_in_the_future(cls, v: date | None) -> date | None:
        """A pet born tomorrow is a typo, and it breaks age arithmetic later."""
        if v is not None and v > date.today():
            raise ValueError("date_of_birth cannot be in the future")
        return v


class PetCreate(_PetBase):
    """A new pet. name and species are the only required fields.

    `owner_id` is here rather than on PetUpdate on purpose. Staff have no
    client_profile of their own, so a vet booking in a walk-in has to say who the
    pet belongs to; the router decides who may send it (see routers/pets.py).
    Re-parenting an *existing* pet is a different, more dangerous operation, so
    PetUpdate omits the field entirely and extra="forbid" turns it into a 422.
    """

    name: str = Field(min_length=1, max_length=80)
    species: str = Field(min_length=1, max_length=40)
    # Matches the column default, so an omitted sex is UNKNOWN rather than NULL.
    sex: Sex = Sex.UNKNOWN
    owner_id: int | None = Field(default=None, gt=0)


class PetUpdate(_PetBase):
    """A partial update. Every field optional -- but not *all* of them omitted."""

    @model_validator(mode="after")
    def _not_empty(self) -> "PetUpdate":
        # model_fields_set is what distinguishes "sent as null" from "not sent",
        # which is the same distinction the router relies on via exclude_unset.
        if not self.model_fields_set:
            raise ValueError("provide at least one field to update")
        return self


class PetOut(BaseModel):
    """A pet as the API describes them."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    name: str
    species: str
    breed: str | None = None
    sex: Sex
    date_of_birth: date | None = None
    weight_kg: float | None = None
    notes: str | None = None
