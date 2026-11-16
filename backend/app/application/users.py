from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.users import Locale, User, normalize_email
from app.infrastructure.db.repositories import UserRepository


class UserAlreadyExists(Exception):
    pass


class InvalidEmail(ValueError):
    pass


# Same validation as the login endpoint, so operators cannot create unusable accounts.
_EMAIL = TypeAdapter(EmailStr)


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._users = UserRepository(db)

    async def update_preferred_locale(self, user: User, locale: Locale) -> User:
        updated = await self._users.set_preferred_locale(user.id, locale)
        if updated is None:
            raise LookupError("user disappeared during update")
        await self._db.commit()
        return updated

    async def create_user(self, *, email: str, preferred_locale: Locale) -> User:
        """Operator-only (CLI). There is no self-service sign-up in the MVP."""
        try:
            email = normalize_email(_EMAIL.validate_python(email))
        except ValidationError as exc:
            raise InvalidEmail(email) from exc
        if await self._users.get_by_email(email):
            raise UserAlreadyExists(email)
        user = await self._users.add(email=email, preferred_locale=preferred_locale)
        await self._db.commit()
        return user
