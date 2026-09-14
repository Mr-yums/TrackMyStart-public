from __future__ import annotations

from sqlalchemy import select

from yumnews.domain.models import LoginAttempt
from yumnews.repositories.base import Repository


class LoginAttemptRepository(Repository[LoginAttempt]):
    model = LoginAttempt

    def find(self, email: str, ip_address: str) -> LoginAttempt | None:
        stmt = select(LoginAttempt).where(
            LoginAttempt.email == email.lower(), LoginAttempt.ip_address == ip_address
        )
        return self.session.scalar(stmt)

    def get_or_create(self, email: str, ip_address: str) -> LoginAttempt:
        attempt = self.find(email, ip_address)
        if attempt is None:
            attempt = LoginAttempt(
                email=email.lower(), ip_address=ip_address, failed_count=0
            )
            self.add(attempt)
        return attempt
