#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#   Copyright 2021 Kaede Hoshikawa
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

"""Utilities for HTTP standard."""

from http.cookies import SimpleCookie as HttpCookies  # noqa: F401
from typing import Optional, Tuple, Union
import calendar
import datetime
import email.utils
import time

__all__ = ["format_timestamp", "HttpCookies"]


_TimeTuple = Tuple[int, int, int, int, int, int, int, int]


def format_timestamp(
    ts: Optional[
        Union[int, float, _TimeTuple, time.struct_time, datetime.datetime]
    ] = None
) -> str:
    """Make an HTTP compatible timestamp."""
    if ts is None:
        ts = time.time()

    if isinstance(ts, (int, float)):
        pass

    elif isinstance(ts, (tuple, time.struct_time)):
        ts = calendar.timegm(ts)

    elif isinstance(ts, datetime.datetime):  # noqa: SIM106
        ts = calendar.timegm(ts.utctimetuple())

    else:
        raise TypeError("unknown timestamp type: {}".format(ts))

    return email.utils.formatdate(ts, usegmt=True)
