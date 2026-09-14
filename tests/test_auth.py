import pytest

from yumnews.services.auth_service import MAX_FAILED_ATTEMPTS, Credentials
from yumnews.services.errors import AuthenticationError, ThrottledError, ValidationError


def test_register_hashes_password_and_sends_verification(container):
    with container.db.session_scope() as session:
        user = container.auth.register(
            session, "A@Example.com", "motdepasse123", "Alice"
        )
        assert user.email == "a@example.com"
        assert user.password_hash != "motdepasse123" and user.password_hash.startswith(
            "scrypt:"
        )
    assert container.mailer.sent[-1].to == "a@example.com"
    assert "/verification/" in container.mailer.sent[-1].text


def test_register_rejects_duplicates_and_weak_passwords(container, user):
    with container.db.session_scope() as session:
        with pytest.raises(ValidationError):
            container.auth.register(session, "yums@example.com", "motdepasse123", "Dup")
        with pytest.raises(ValidationError):
            container.auth.register(session, "new@example.com", "court", "New")


def test_authenticate_and_lockout(container, user):
    with container.db.session_scope() as session:
        assert (
            container.auth.authenticate(
                session, Credentials("yums@example.com", "motdepasse123"), "1.2.3.4"
            ).id
            == user
        )
    for _ in range(MAX_FAILED_ATTEMPTS):
        session = container.db.session()
        with pytest.raises(AuthenticationError):
            container.auth.authenticate(
                session, Credentials("yums@example.com", "faux"), "1.2.3.4"
            )
        session.commit()
    with pytest.raises(ThrottledError):
        container.auth.authenticate(
            container.db.session(),
            Credentials("yums@example.com", "motdepasse123"),
            "1.2.3.4",
        )
    # Une autre IP n'est pas bloquée
    with container.db.session_scope() as session:
        container.auth.authenticate(
            session, Credentials("yums@example.com", "motdepasse123"), "9.9.9.9"
        )


def test_verification_and_password_reset_tokens(container, user):
    token = container.mailer.sent[-1].text.split("/verification/")[1].split()[0]
    with container.db.session_scope() as session:
        assert container.auth.verify_email(session, token).email_verified is True
        container.auth.request_password_reset(session, "yums@example.com")
        container.auth.request_password_reset(
            session, "inconnu@example.com"
        )  # silencieux
    reset = container.mailer.sent[-1].text.split("/reinitialiser/")[1].split()[0]
    with container.db.session_scope() as session:
        container.auth.reset_password(session, reset, "nouveaumdp456")
        with pytest.raises(ValidationError):  # jeton à usage unique
            container.auth.reset_password(session, reset, "encoreunautre789")
        container.auth.authenticate(
            session, Credentials("yums@example.com", "nouveaumdp456"), "1.1.1.1"
        )


def test_web_login_flow(client, user):
    r = client.post(
        "/connexion", data={"email": "yums@example.com", "password": "motdepasse123"}
    )
    assert r.status_code == 302 and r.headers["Location"].endswith("/app")
    assert client.get("/app").status_code == 200
    assert client.get("/api/me").get_json()["user"]["display_name"] == "Yums"
    client.post("/deconnexion")
    assert client.get("/api/me").status_code == 401
