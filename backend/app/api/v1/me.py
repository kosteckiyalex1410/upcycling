import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict

from app.api.v1.deps import CurrentUser, DbDep
from app.application.users import UserService
from app.domain.users import Locale, User

router = APIRouter(prefix="/me", tags=["me"])


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    preferred_locale: Locale

    @classmethod
    def from_user(cls, user: User) -> "MeResponse":
        return cls(id=user.id, email=user.email, preferred_locale=user.preferred_locale)


class UpdateMeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_locale: Locale


@router.get("", response_model=MeResponse)
async def get_me(user: CurrentUser) -> MeResponse:
    return MeResponse.from_user(user)


@router.patch("", response_model=MeResponse)
async def update_me(body: UpdateMeRequest, user: CurrentUser, db: DbDep) -> MeResponse:
    updated = await UserService(db).update_preferred_locale(user, body.preferred_locale)
    return MeResponse.from_user(updated)
