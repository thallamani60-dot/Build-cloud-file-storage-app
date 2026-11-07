from fastapi import APIRouter, Depends, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.limiter import limiter
from app.database.session import get_db
from app.schemas.auth import TokenResponse, UserCreate, UserRead
from app.services import auth_service


router = APIRouter()


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def register(request: Request, payload: UserCreate, db: Session = Depends(get_db)):
    return auth_service.register(db, str(payload.email), payload.password)


@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    _, access_token, expires_in = auth_service.authenticate(db, form.username, form.password)
    return TokenResponse(access_token=access_token, expires_in=expires_in)
