from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import APIError
from app.core.security import create_access_token, hash_password, password_hash, verify_password
from app.models import User
from app.repositories import user_repository


_DUMMY_PASSWORD_HASH = password_hash.hash("constant-time-login-check")


def register(db: Session, email: str, password: str) -> User:
    normalized_email = email.strip().lower()
    if user_repository.get_by_email(db, normalized_email):
        raise APIError(409, "email_already_registered", "An account with this email already exists")
    try:
        return user_repository.create(db, normalized_email, hash_password(password))
    except IntegrityError as exc:
        db.rollback()
        raise APIError(409, "email_already_registered", "An account with this email already exists") from exc


def authenticate(db: Session, email: str, password: str) -> tuple[User, str, int]:
    user = user_repository.get_by_email(db, email.strip().lower())
    if not verify_password(password, user.hashed_password if user else _DUMMY_PASSWORD_HASH):
        raise APIError(401, "invalid_credentials", "Email or password is incorrect")
    if not user or not user.is_active:
        raise APIError(401, "invalid_credentials", "Email or password is incorrect")
    token, expires_in = create_access_token(user.id)
    return user, token, expires_in
