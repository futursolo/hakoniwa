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

from typing import (
    Any,
    AnyStr,
    Awaitable,
    Callable,
    Dict,
    Optional,
    Pattern,
    Type,
    Union,
)
import asyncio
import asyncio.base_events
import concurrent.futures
import datetime
import os
import ssl

import destination
import sketchbook

# from . import responses
from . import (
    constants,
    exceptions,
    handlers,
    impl_lambda,
    impl_magichttp,
    requests,
    security,
)

__all__ = ["Application"]


_DELTA_30_DAYS: datetime.timedelta = datetime.timedelta(days=30)


class Application:
    class DefaultHandler(handlers.RequestHandler):
        async def before(self) -> None:
            raise exceptions.HttpError(constants.HttpStatusCode.NOT_FOUND)

    def __init__(
        self,
        *,
        sketch_path: Optional[str] = None,
        skt_ctx: Optional[sketchbook.AsyncioSketchContext] = None,
        skt_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None,
        csrf_protect: bool = False,
        static_path: Optional[str] = None,
        static_handler_path: Union[
            str, Pattern[str]
        ] = r"^static/(?P<file>.*?)$",
        security_secret: Optional[
            Union[str, bytes, security.BaseSecurityContext]
        ] = None,
        secure_cookie_max_age: datetime.timedelta = _DELTA_30_DAYS,
        safe_cookies: bool = True,
    ) -> None:
        self.handlers: destination.Dispatcher[
            Type[handlers.BaseRequestHandler]
        ] = destination.Dispatcher()

        if sketch_path is not None:
            if skt_ctx is None:
                loop = asyncio.get_event_loop()
                skt_ctx = sketchbook.AsyncioSketchContext(
                    cache_sketches=False if loop.get_debug() else True
                )

            self._skt_finder: Optional[
                sketchbook.AsyncSketchFinder
            ] = sketchbook.AsyncSketchFinder(
                sketch_path, executor=skt_executor, skt_ctx=skt_ctx
            )

        else:
            self._skt_finder = None

        self._csrf_protect = csrf_protect

        if static_path is not None:
            static_path_2 = static_path

            class StaticFileHandler(handlers.StaticFileHandler):
                static_path = static_path_2

            self.handlers.add(
                destination.ReRule(static_handler_path, StaticFileHandler),
                name="static",
            )

        if security_secret is not None:
            if isinstance(security_secret, security.BaseSecurityContext):
                self._sec_ctx: Optional[
                    security.BaseSecurityContext
                ] = security_secret

            else:
                if isinstance(security_secret, str):
                    security_secret = security_secret.encode("utf-8")

                self._sec_ctx = security.HmacSha256SecurityContext(
                    security_secret
                )

        else:
            self._sec_ctx = None

        self._secure_cookie_max_age = secure_cookie_max_age
        self._safe_cookies = safe_cookies

    async def process_request(self, request: requests.Request) -> None:
        try:
            resolved_path = self.handlers.resolve(request.path)
            handler: handlers.BaseRequestHandler = resolved_path.identifier(
                self, request, resolved_path.kwargs
            )

        except destination.NoMatchesFound:
            handler = self.DefaultHandler(self, request, {})

        await handler._process_request()

    async def process_lambda_request(
        self, event: Dict[str, Any]
    ) -> Dict[str, Any]:
        request = impl_lambda.LambdaRequest(event)
        await self.process_request(request)

        response = await request._get_final_response()
        return response.translate()

    def make_server(self) -> Callable[[], asyncio.Protocol]:
        """Make an asyncio server factory."""
        return lambda: impl_magichttp.MagichttpServerProtocol(self)

    def _ensure_tls_context(
        self, tls_ctx: Optional[Union[bool, ssl.SSLContext]] = None
    ) -> Optional[ssl.SSLContext]:
        if tls_ctx:
            if isinstance(tls_ctx, bool):
                _context: Optional[
                    ssl.SSLContext
                ] = ssl.create_default_context()

            else:
                _context = tls_ctx

        else:
            _context = None

        return _context

    def listen(
        self,
        port: int,
        address: str = "localhost",
        *,
        tls_ctx: Optional[Union[bool, ssl.SSLContext]] = None,
        start_serving: bool = True,
    ) -> Awaitable[asyncio.events.AbstractServer]:
        """
        Make a server and listen to the specified port and address.

        :arg port: port number to bind
        :arg address: ip address or hostname to bind
        :arg tls_ctx: TLS Context or True for default tls context None or False
            to disable tls
        :arg start_serviing: Defines whether to start serving by default.
            See asyncio's documentation for more details.
        """
        loop = asyncio.get_event_loop()

        coro = loop.create_server(
            self.make_server(),
            address,
            port,
            ssl=self._ensure_tls_context(tls_ctx),
            start_serving=start_serving,
        )

        return loop.create_task(coro)

    def listen_unix(
        self,
        path: os.PathLike[AnyStr],
        *,
        tls_ctx: Optional[Union[bool, ssl.SSLContext]] = None,
        start_serving: bool = True,
    ) -> Awaitable[asyncio.events.AbstractServer]:
        """
        Make a server and listens to a specific UNIX domain socket.

        :arg path: the path to bind
        :arg tls_ctx: TLS Context or True for default tls context None or False
            to disable tls
        :arg start_serviing: Defines whether to start serving by default.
            See asyncio's documentation for more details.
        """
        loop = asyncio.get_event_loop()

        coro = loop.create_unix_server(
            self.make_server(),
            path=path,  # type: ignore
            ssl=self._ensure_tls_context(tls_ctx),
            start_serving=start_serving,
        )

        return loop.create_task(coro)
