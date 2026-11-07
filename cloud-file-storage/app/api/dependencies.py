import jwt
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import APIError
from app.core.security import decode_access_token
from app.database.session import get_db
from app.models import User
from app.repositories import user_repository


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    try:
        user_id = decode_access_token(token)
    except jwt.ExpiredSignatureError as exc:
        raise APIError(401, "token_expired", "Access token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise APIError(401, "invalid_token", "Access token is invalid") from exc

    user = user_repository.get_by_id(db, user_id)
    if not user or not user.is_active:
        raise APIError(401, "invalid_token", "Access token is invalid")
    return user
