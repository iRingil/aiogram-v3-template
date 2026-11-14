"""Helpers shared by the tests."""

from unittest.mock import NonCallableMock

__all__: tuple[str, ...] = ("mocked",)


def mocked(obj: object) -> NonCallableMock:
    """
    Returns an object that a test replaced with a mock, typed as the mock it is.

    The attributes of the tested classes keep their real types for the type checker, so the mock
    assertions and the attributes set on a mock are reachable only through this function.

    :param obj: The object expected to be a mock.
    :return: The same object.
    :raises TypeError: if the object is not a mock.
    """
    if not isinstance(obj, NonCallableMock):
        raise TypeError(f"{obj!r} is not a mock")
    return obj
