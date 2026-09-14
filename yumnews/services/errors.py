"""Exceptions métier : les contrôleurs les traduisent en codes HTTP."""


class DomainError(Exception):
    status_code = 400

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.__class__.__name__


class ValidationError(DomainError):
    status_code = 400


class AuthenticationError(DomainError):
    status_code = 401


class ThrottledError(DomainError):
    status_code = 429


class AccessDeniedError(DomainError):
    """Fonctionnalité réservée au plan Premium (HTTP 402 : Payment Required)."""

    status_code = 402


class PaymentError(DomainError):
    status_code = 402


class CouponError(DomainError):
    """Code promo invalide, expiré ou épuisé (HTTP 400)."""

    status_code = 400


class NotFoundError(DomainError):
    status_code = 404
