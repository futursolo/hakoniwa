#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#   Copyright 2019 Kaede Hoshikawa
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

"""Generic Utilities."""

from __future__ import annotations

from typing import Any, Callable, Dict, Generic, Sequence, TypeVar, Union
import functools
import typing

from typing_extensions import Protocol

_T = TypeVar("_T")


class _JsonList(Protocol):
    def __getitem__(self, index: int) -> Json:
        ...

    # hack to enforce an actual list
    def sort(self) -> None:
        ...


class _JsonDict(Protocol):
    def __getitem__(self, key: str) -> Json:
        ...

    # hack to enforce an actual dict
    @staticmethod
    @typing.overload
    def fromkeys(seq: Sequence[Any]) -> Dict[Any, Any]:
        ...

    @staticmethod  # noqa: F811
    @typing.overload
    def fromkeys(seq: Sequence[Any], value: Any) -> Dict[Any, Any]:
        ...


Json = Union[str, int, float, bool, None, _JsonList, _JsonDict]


class _LazyPropertyWrapper(Generic[_T]):
    def __init__(self, func: Callable[[Any], _T]) -> None:
        self.func = func
        functools.update_wrapper(self, func)

    def __get__(self, obj: Any, *args: Any, **kwargs: Any) -> _T:
        if obj is None:
            return self  # type: ignore
        val = self.func(obj)  # noqa: VNE002
        obj.__dict__[self.func.__name__] = val
        return val


def lazy_property(func: Callable[[Any], _T]) -> _LazyPropertyWrapper[_T]:
    """
    A Cached Property Decorator.

    References:
    https://en.wikipedia.org/wiki/Lazy_evaluation
    https://github.com/faif/python-patterns/blob/master/creational/
    lazy_evaluation.py
    """
    return _LazyPropertyWrapper(func)
