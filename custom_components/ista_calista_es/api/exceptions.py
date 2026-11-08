"""Excepciones de la capa de acceso al portal Calista."""

from __future__ import annotations


class CalistaError(Exception):
    """Error genérico del portal."""


class CannotConnect(CalistaError):
    """No se puede contactar con el portal (timeout, red, HTTP inesperado)."""


class InvalidAuth(CalistaError):
    """Keycloak ha rechazado las credenciales."""


class AuthActionRequired(CalistaError):
    """Keycloak pide una acción en la web (cambiar contraseña, aceptar condiciones, 2FA…)."""


class SessionExpired(CalistaError):
    """La sesión del portal no es válida (redirección al login o error 500)."""


class ParseError(CalistaError):
    """La respuesta del portal no tiene el formato esperado."""
