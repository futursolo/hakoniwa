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

"""This Implements AWS Lambda support for hakoniwa."""

from typing import Any, Dict, List, Mapping, Optional, Tuple
import asyncio
import base64

import magicdict

from . import constants, exceptions, requests, responses
from .utils import lazy_property


class LambdaRequest(requests.Request):
    """Request for AWS Lambda."""

    def __init__(self, event: Dict[str, Any]) -> None:
        """Initialise LambdaRequest."""
        self._event = event

        if event["isBase64Encoded"]:
            self._body = base64.b64decode(event["body"])

        else:
            self._body = event["body"].encode() if event["body"] else b""

        self._method = constants.HttpRequestMethod(event["httpMethod"].upper())
        self._version = constants.HttpVersion(
            event["requestContext"]["protocol"]
        )

        self._uri: str = event.get("path", "/")
        self._authority: Optional[str] = event["requestContext"].get(
            "domainName", None
        )
        queries_list: List[Tuple[str, str]] = []
        for key, values in (
            event.get("multiValueQueryStringParameters", {}) or {}
        ).items():
            for value in values:
                queries_list.append((key, value))

        self._queries: magicdict.FrozenTolerantMagicDict[
            str, str
        ] = magicdict.FrozenTolerantMagicDict(queries_list)

        header_list: List[Tuple[str, str]] = []
        for key, values in event["multiValueHeaders"].items():
            for value in values:
                header_list.append((key, value))

        self._headers: magicdict.FrozenTolerantMagicDict[
            str, str
        ] = magicdict.FrozenTolerantMagicDict(header_list)

        scheme_str = self._headers.get_first("x-forwarded-proto", "").lower()
        self._scheme = constants.HttpScheme(scheme_str) if scheme_str else None

        self._res_fur: asyncio.Future["LambdaResponse"] = asyncio.Future()

    @property
    def method(self) -> constants.HttpRequestMethod:
        """Return the request method."""
        return self._method

    @property
    def version(self) -> constants.HttpVersion:
        """Return the request version."""
        return self._version

    @property
    def uri(self) -> str:
        """Return the request URI."""
        return self._uri

    @lazy_property
    def queries(self) -> magicdict.FrozenTolerantMagicDict[str, str]:
        """Return the parsed queries."""
        return self._queries

    @property
    def authority(self) -> str:
        """Return the authority of the request."""
        if self._authority is None:
            raise AttributeError("Authority is not available.")

        return self._authority

    @property
    def scheme(self) -> constants.HttpScheme:
        """Return the scheme of the request."""
        if self._scheme is None:
            raise AttributeError("Scheme is not available.")

        return self._scheme

    @property
    def headers(self) -> magicdict.FrozenTolerantMagicDict[str, str]:
        """Return the headers of the request."""
        return self._headers

    @property
    def body(self) -> bytes:
        """Return the body of the request."""
        return self._body

    async def read(self) -> bytes:
        """
        Read the body of the request.

        .. note:

           This has no effect on LambdaRequest and returns the body
           immediately.
        """
        return self.body

    async def write_response(
        self,
        status_code: constants.HttpStatusCode,
        *,
        headers: Optional[Mapping[str, str]] = None,
    ) -> "LambdaResponse":
        """Send the response."""
        if self._res_fur.done():
            raise exceptions.HttpError(
                500, "You can only write response once."
            )

        response = LambdaResponse(
            self,
            status_code=status_code,
            headers=magicdict.FrozenTolerantMagicDict(headers or {}),
        )

        self._res_fur.set_result(response)

        return response

    async def _get_final_response(self) -> "LambdaResponse":
        response = await self._res_fur
        await response.wait_finished()

        return response


class LambdaResponse(responses.Response):
    """Request for AWS Lambda."""

    def __init__(
        self,
        request: LambdaRequest,
        *,
        status_code: constants.HttpStatusCode,
        headers: magicdict.FrozenTolerantMagicDict[str, str],
    ) -> None:
        """Initialise LambdaResponse."""
        self._request = request
        self._status_code = status_code
        self._headers = headers

        self._body_chunks: List[bytes] = []
        self._finished = asyncio.Event()

    @property
    def request(self) -> LambdaRequest:
        """Return the correspoding request."""
        return self._request

    @property
    def status_code(self) -> constants.HttpStatusCode:
        """Return the status code of the response."""
        return self._status_code

    @property
    def version(self) -> constants.HttpVersion:
        """Return the http version of the response."""
        return self._request.version

    @property
    def headers(self) -> magicdict.FrozenTolerantMagicDict[str, str]:
        """Return the headers of the response."""
        return self._headers

    async def write(self, data: bytes) -> None:
        """Write a chunk of response body."""
        if data:
            self._body_chunks.append(data)

    async def finish(self) -> None:
        """Finish the response."""
        self._finished.set()

    def finished(self) -> bool:
        """Return :code:`True` if the response is finished."""
        return self._finished.is_set()

    async def wait_finished(self) -> None:
        """Wait until the response finishes."""
        await self._finished.wait()

    def translate(self) -> Dict[str, Any]:
        """Translate the LambdaResponse object to AWS Lambda Response."""
        assert self.finished(), "This response is not finished."

        header_lists: Dict[str, List[str]] = {}
        for (header_name, header_val) in self.headers.items():
            if header_name in ("content-length",):
                continue

            if header_name not in header_lists.keys():
                header_lists[header_name] = []

            header_lists[header_name].append(header_val)

        body_bytes = b"".join(self._body_chunks)

        try:
            body_str = body_bytes.decode()
            b64_encoded = False

        except UnicodeDecodeError:
            body_str = base64.b64encode(body_bytes).decode()
            b64_encoded = True

        return {
            "isBase64Encoded": b64_encoded,
            "statusCode": int(self.status_code),
            "multiValueHeaders": header_lists,
            "body": body_str,
        }
