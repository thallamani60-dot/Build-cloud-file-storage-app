from botocore.exceptions import ClientError
from botocore.exceptions import EndpointConnectionError
import pytest
from pydantic import ValidationError

from app.core.config import Settings, settings
from app.services import s3_service
from tests.conftest import create_account


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def upload_pdf(client, token: str, filename: str = "report.pdf"):
    return client.post(
        "/api/v1/files/upload",
        headers=auth(token),
        files={"file": (filename, b"%PDF-1.7\nfile-content", "application/pdf")},
    )


def test_health_and_readiness(api_client):
    assert api_client.get("/").json()["status"] == "healthy"
    assert api_client.get("/health/ready").json()["status"] == "ready"
    landing_page = api_client.get("/app")
    assert landing_page.status_code == 200
    assert landing_page.headers["content-type"].startswith("text/html")
    assert "Your files." in landing_page.text
    assert "In your corner." in landing_page.text


def test_production_requires_a_configured_jwt_secret(monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(ValidationError, match="SECRET_KEY is required in production"):
        Settings(_env_file=None, environment="production")
    with pytest.raises(ValidationError, match="Replace the sample SECRET_KEY"):
        Settings(
            _env_file=None,
            environment="production",
            secret_key="replace-with-generated-secrets-token_urlsafe-value",
        )


def test_registration_and_login_errors(api_client):
    response = api_client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "correct-horse-battery-staple"},
    )
    assert response.status_code == 201
    assert "hashed_password" not in response.text

    duplicate = api_client.post(
        "/api/v1/auth/register",
        json={"email": "new@example.com", "password": "correct-horse-battery-staple"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "email_already_registered"

    bad_login = api_client.post(
        "/api/v1/auth/login",
        data={"username": "new@example.com", "password": "wrong-password"},
    )
    assert bad_login.status_code == 401
    assert bad_login.headers["www-authenticate"] == "Bearer"


def test_file_endpoints_and_metadata(api_client, account, storage):
    uploaded = upload_pdf(api_client, account)
    assert uploaded.status_code == 201, uploaded.text
    metadata = uploaded.json()
    assert metadata["original_filename"] == "report.pdf"
    assert metadata["size_bytes"] > 0
    second_upload = upload_pdf(api_client, account, "summary.pdf")
    assert second_upload.status_code == 201

    listed = api_client.get("/api/v1/files?limit=1&offset=0&extension=pdf", headers=auth(account))
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert listed.json()["limit"] == 1
    assert len(listed.json()["items"]) == 1

    filtered = api_client.get("/api/v1/files?q=report", headers=auth(account))
    assert filtered.json()["total"] == 1

    details = api_client.get(f"/api/v1/files/{metadata['id']}", headers=auth(account))
    assert details.status_code == 200

    downloaded = api_client.get(f"/api/v1/files/{metadata['id']}/download", headers=auth(account))
    assert downloaded.status_code == 200
    assert downloaded.content == b"%PDF-1.7\nfile-content"
    assert "attachment; filename*=UTF-8''report.pdf" == downloaded.headers["content-disposition"]

    signed_url = api_client.get(
        f"/api/v1/files/{metadata['id']}/presigned-url", headers=auth(account)
    )
    assert signed_url.status_code == 200
    assert "X-Amz-Signature" in signed_url.json()["url"]
    assert signed_url.json()["expires_in"] == settings.presigned_url_expire_seconds

    object_list = storage.list_objects_v2(Bucket=settings.s3_bucket_name)
    assert object_list["KeyCount"] == 2
    assert all(item["Key"].startswith("users/") for item in object_list["Contents"])

    deleted = api_client.delete(f"/api/v1/files/{metadata['id']}", headers=auth(account))
    assert deleted.status_code == 204
    missing = api_client.get(f"/api/v1/files/{metadata['id']}", headers=auth(account))
    assert missing.status_code == 404


def test_users_cannot_access_each_others_files(api_client, account, storage):
    uploaded = upload_pdf(api_client, account)
    file_id = uploaded.json()["id"]
    other_token = create_account(api_client, "other@example.com")

    for method, path in (
        (api_client.get, f"/api/v1/files/{file_id}"),
        (api_client.get, f"/api/v1/files/{file_id}/download"),
        (api_client.get, f"/api/v1/files/{file_id}/presigned-url"),
        (api_client.delete, f"/api/v1/files/{file_id}"),
    ):
        response = method(path, headers=auth(other_token))
        assert response.status_code == 404

    assert api_client.get("/api/v1/files", headers=auth(other_token)).json()["total"] == 0


def test_authentication_and_invalid_uploads(api_client, account, monkeypatch):
    unauthenticated = api_client.get("/api/v1/files")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "not_authenticated"

    invalid_extension = api_client.post(
        "/api/v1/files/upload",
        headers=auth(account),
        files={"file": ("payload.exe", b"x", "application/octet-stream")},
    )
    assert invalid_extension.status_code == 415

    monkeypatch.setattr(settings, "max_upload_bytes", 4)
    too_large = api_client.post(
        "/api/v1/files/upload",
        headers=auth(account),
        files={"file": ("notes.txt", b"12345", "text/plain")},
    )
    assert too_large.status_code == 413


def test_storage_permission_errors_are_safe(api_client, account, storage, monkeypatch):
    class DeniedS3:
        def put_object(self, **kwargs):
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "private detail"}},
                "PutObject",
            )

    monkeypatch.setattr(s3_service, "get_s3_client", lambda: DeniedS3())
    response = upload_pdf(api_client, account)
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "storage_permission_error"
    assert "private detail" not in response.text


def test_storage_network_failure_returns_service_unavailable(api_client, account, storage, monkeypatch):
    class OfflineS3:
        def put_object(self, **kwargs):
            raise EndpointConnectionError(endpoint_url="https://s3.example.invalid")

    monkeypatch.setattr(s3_service, "get_s3_client", lambda: OfflineS3())
    response = upload_pdf(api_client, account)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "storage_unavailable"
