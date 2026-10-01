from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import HSKLevel


class RegistrationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date
    nationality: str = Field(min_length=2, max_length=100)
    passport_number: str = Field(min_length=5, max_length=32)
    phone_number: str = Field(min_length=7, max_length=24)
    parent_phone_number: str = Field(min_length=7, max_length=24)
    hsk_level: HSKLevel

    @field_validator("date_of_birth")
    @classmethod
    def date_of_birth_cannot_be_in_the_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("date of birth cannot be in the future")
        return value

    @field_validator("passport_number")
    @classmethod
    def validate_passport_number(cls, value: str) -> str:
        normalized = value.upper()
        if not normalized.replace("-", "").isalnum():
            raise ValueError("passport number has an invalid format")
        return normalized

    @field_validator("phone_number", "parent_phone_number")
    @classmethod
    def validate_phone_number(cls, value: str) -> str:
        allowed = set("0123456789+() .-")
        digit_count = sum(character.isdigit() for character in value)
        if not set(value) <= allowed or digit_count < 7:
            raise ValueError("phone number has an invalid format")
        return value


class RegistrationUpdate(RegistrationCreate):
    """Validated fields staff may correct while a registration is pending."""
