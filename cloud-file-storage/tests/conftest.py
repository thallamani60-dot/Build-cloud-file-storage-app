import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-only-secret-key-for-cloud-file-storage-suite"
os.environ["S3_BUCKET_NAME"] = "test-cloud-file-storage"
os.environ["AWS_REGION"] = "ap-south-1"
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
os.environ["RATE_LIMIT_STORAGE_URI"] = "memory://"

import pytest
from fastapi.testclient import TestClient
from moto import mock_aws
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.limiter import limiter
from app.database.base import Base
from app.database.session import get_db
from app.models import FileRecord, User  # noqa: F401 - register metadata
from app.services import s3_service


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    Base.metadata.drop_all(test_engine)
    Base.metadata.create_all(test_engine)
    with Session(test_engine, expire_on_commit=False) as session:
        yield session
    Base.metadata.drop_all(test_engine)


@pytest.fixture
def storage(db_session, monkeypatch):
    from app.core.config import settings

    with mock_aws():
        client = __import__("boto3").client("s3", region_name=settings.aws_region)
        client.create_bucket(
            Bucket=settings.s3_bucket_name,
            CreateBucketConfiguration={"LocationConstraint": settings.aws_region},
        )
        monkeypatch.setattr(s3_service, "get_s3_client", lambda: client)
        yield client


@pytest.fixture
def api_client(db_session, storage, monkeypatch):
    from app.main import app

    limiter.enabled = False

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()
    limiter.enabled = True


@pytest.fixture
def account(api_client):
    return create_account(api_client, "owner@example.com")


def create_account(client: TestClient, email: str) -> str:
    registration = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "correct-horse-battery-staple"},
    )
    assert registration.status_code == 201, registration.text
    login = client.post(
        "/api/v1/auth/login",
        data={"username": email, "password": "correct-horse-battery-staple"},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]
