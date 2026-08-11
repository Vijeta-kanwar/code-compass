"""Module docstring."""

import os
from typing import Any

CONSTANT = 42


def plain(x: int) -> int:
    return x + 1


@staticmethod
def decorated(y):
    """Has a decorator above the def."""
    return y


async def fetch(url: str) -> Any:
    return await _get(url)


class Widget:
    """A widget."""

    registry: dict = {}

    def __init__(self, name: str):
        self.name = name

    @property
    def label(self) -> str:
        return self.name

    @label.setter
    def label(self, value: str) -> None:
        self.name = value

    async def refresh(self) -> None:
        await _get(self.name)

    def outer(self):
        def inner():
            return 1
        return inner()