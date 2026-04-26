"""Wrapper around the official ``openai`` SDK.

Centralizes:

- Authentication (FR-8.1, NFR-3.2 — key never logged)
- Endpoint selection (generations vs edits)
- Request shaping per the resolved capability matrix in
  :mod:`photo_mcp.models`
- Retry / classification per :mod:`photo_mcp.retry`
- Response normalization to a single :class:`ImageResponse` type that
  tools consume

The module assumes ``openai >= 1.50`` (see pyproject pin). It is the
ONLY place in the codebase that imports ``openai``; everything else
talks to :class:`OpenAIImageClient` so swapping or mocking is a
one-file change.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from photo_mcp import retry
from photo_mcp.logging import StructuredLogger, get_logger
from photo_mcp.models import (
    BackgroundPolicy,
    InputFidelity,
    ModelId,
    ModerationLevel,
    OutputFormat,
    QualityLevel,
    ResponseFormat,
)


# -----------------------------------------------------------------------------
# Response normalization
# -----------------------------------------------------------------------------


@dataclass(slots=True)
class ImageData:
    """One generated image returned by the API.

    The API returns either ``b64_json`` (default) or ``url``. We carry
    whichever was returned; callers convert to bytes for writing.
    """

    b64_json: str | None = None
    url: str | None = None
    revised_prompt: str | None = None


@dataclass(slots=True)
class ApiUsage:
    """Token usage reported by the response.

    Mirrors OpenAI's ``response.usage`` structure for image endpoints.
    Tools forward this into the sidecar so the photographer can audit
    actual billed usage post-hoc.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_text_tokens: int = 0
    input_image_tokens: int = 0


@dataclass(slots=True)
class ImageResponse:
    """Normalized response from either /generations or /edits.

    Tools consume this; the OpenAI SDK's per-version response object
    is encapsulated here so SDK upgrades only touch this module.
    """

    images: list[ImageData]
    usage: ApiUsage
    model: ModelId
    request_ms: int


@dataclass(slots=True)
class StreamEvent:
    """One streamed event during a streaming generation/edit.

    OpenAI's streaming protocol surfaces partial-image frames and a
    final completion event. This dataclass is what the server hands
    upstream as MCP ``tools/progress`` notifications.
    """

    kind: str       # "partial" | "completed" | "error"
    index: int = 0  # which partial frame (0..partial_images-1) or 0 on completed
    b64_json: str | None = None
    revised_prompt: str | None = None
    usage: ApiUsage | None = None
    error: str | None = None


# -----------------------------------------------------------------------------
# Errors
# -----------------------------------------------------------------------------


class OpenAIClientError(Exception):
    """Wrapper raised by ``OpenAIImageClient`` for non-retriable failures."""

    error_type: str = "openai_error"

    def __init__(self, message: str, *, status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class AuthError(OpenAIClientError):
    error_type = "auth_error"


class InvalidRequest(OpenAIClientError):
    error_type = "invalid_request"


class InputTooLarge(OpenAIClientError):
    error_type = "input_too_large"


class ModerationBlocked(OpenAIClientError):
    error_type = "moderation_blocked"


# -----------------------------------------------------------------------------
# Client
# -----------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class GenerationRequest:
    """Parameters for /v1/images/generations.

    All optional fields default to ``None`` meaning "let the API pick
    its default" — we don't substitute our own defaults here so the
    user / tool input is the only source of truth. The tool layer
    fills in defaults from Config before constructing this dataclass.
    """

    model: ModelId
    prompt: str
    n: int = 1
    size: str | None = None
    quality: QualityLevel | None = None
    output_format: OutputFormat | None = None
    output_compression: int | None = None
    background: BackgroundPolicy | None = None
    moderation: ModerationLevel | None = None
    # NOTE: no response_format field — DALL-E parameter, rejected by gpt-image.


@dataclass(frozen=True, slots=True)
class EditRequest:
    """Parameters for /v1/images/edits (1..16 images, optional mask).

    The image / mask fields hold OPEN file handles or paths the
    SDK can stream from. The caller is responsible for closing
    them after the request returns (we do this via ``_send_edit``).
    """

    model: ModelId
    prompt: str
    image_paths: tuple[Path, ...]
    mask_path: Path | None = None
    n: int = 1
    size: str | None = None
    quality: QualityLevel | None = None
    output_format: OutputFormat | None = None
    output_compression: int | None = None
    input_fidelity: InputFidelity | None = None
    moderation: ModerationLevel | None = None
    # NOTE: no response_format field — DALL-E parameter, rejected by gpt-image.


class OpenAIImageClient:
    """Thin wrapper over the OpenAI SDK's image endpoints.

    Construct with the API key + retry policy + logger. All methods are
    async and return normalized :class:`ImageResponse` objects.

    The client lazy-imports the SDK so importing ``photo_mcp`` doesn't
    require the SDK to be installed at module import time (useful for
    tooling that introspects the package).
    """

    def __init__(
        self,
        *,
        api_key: str,
        retry_policy: retry.RetryPolicy = retry.RetryPolicy(),
        logger: StructuredLogger | None = None,
        base_url: str | None = None,
    ) -> None:
        if not api_key:
            raise AuthError("API key is empty; set OPENAI_API_KEY")
        # Defer SDK import — see class docstring.
        from openai import AsyncOpenAI

        self._sdk = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._retry_policy = retry_policy
        self._log = logger or get_logger()

    # ------------------------------------------------------------------
    # Public dispatch
    # ------------------------------------------------------------------

    async def generate(self, req: GenerationRequest) -> ImageResponse:
        """POST /v1/images/generations with retries + normalization."""
        return await self._with_retries(lambda: self._send_generate(req), endpoint="generations")

    async def edit(self, req: EditRequest) -> ImageResponse:
        """POST /v1/images/edits with retries + normalization."""
        return await self._with_retries(lambda: self._send_edit(req), endpoint="edits")

    async def stream_generate(self, req: GenerationRequest) -> AsyncIterator[StreamEvent]:
        """Streaming variant of generate. Yields StreamEvents as they arrive."""
        async for ev in self._open_stream("generations", req):
            yield ev

    async def stream_edit(self, req: EditRequest) -> AsyncIterator[StreamEvent]:
        """Streaming variant of edit. Yields StreamEvents as they arrive."""
        async for ev in self._open_stream("edits", req):
            yield ev

    # ------------------------------------------------------------------
    # Retry shell
    # ------------------------------------------------------------------

    async def _with_retries(
        self, op: Any, *, endpoint: str
    ) -> ImageResponse:
        def observer(attempt: int, delay: float | None, err: BaseException | None) -> None:
            if err is None:
                self._log.debug("openai_attempt", endpoint=endpoint, attempt=attempt)
            else:
                self._log.warning(
                    "openai_retry",
                    endpoint=endpoint,
                    attempt=attempt,
                    delay_s=delay,
                    error_type=type(err).__name__,
                    error=str(err),
                )

        return await retry.with_retry(
            op,
            policy=self._retry_policy,
            classifier=_classify_openai_error,
            on_attempt=observer,
        )

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    async def _send_generate(self, req: GenerationRequest) -> ImageResponse:
        kwargs = _generation_kwargs(req)
        start = _ms()
        sdk_response = await self._sdk.images.generate(**kwargs)
        return _normalize(sdk_response, model=req.model, request_ms=_ms() - start)

    async def _send_edit(self, req: EditRequest) -> ImageResponse:
        # The SDK accepts file-like objects or tuples of (filename, file, mime).
        # Open every image / mask, send the request, close in a finally so
        # we never leak fds even on exception.
        opened: list[IO[bytes]] = []
        try:
            images = [self._open_for_upload(p, opened) for p in req.image_paths]
            mask = self._open_for_upload(req.mask_path, opened) if req.mask_path else None
            kwargs = _edit_kwargs(req, images, mask)
            start = _ms()
            sdk_response = await self._sdk.images.edit(**kwargs)
            return _normalize(sdk_response, model=req.model, request_ms=_ms() - start)
        finally:
            for fp in opened:
                try:
                    fp.close()
                except OSError:
                    pass

    @staticmethod
    def _open_for_upload(path: Path | None, opened: list[IO[bytes]]) -> IO[bytes] | None:
        if path is None:
            return None
        fp = path.open("rb")
        opened.append(fp)
        return fp

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def _open_stream(
        self, endpoint: str, req: GenerationRequest | EditRequest
    ) -> AsyncIterator[StreamEvent]:
        # OpenAI's image-stream API yields partial-image events plus one
        # final completion. We translate each event to our StreamEvent
        # type. Streaming requests do not retry (the SDK handles the
        # initial connect; mid-stream errors are surfaced as kind="error").
        if endpoint == "generations":
            assert isinstance(req, GenerationRequest)
            kwargs = _generation_kwargs(req) | {"stream": True}
            stream = await self._sdk.images.generate(**kwargs)
        else:
            assert isinstance(req, EditRequest)
            opened: list[IO[bytes]] = []
            images = [self._open_for_upload(p, opened) for p in req.image_paths]
            mask = self._open_for_upload(req.mask_path, opened) if req.mask_path else None
            kwargs = _edit_kwargs(req, images, mask) | {"stream": True}
            stream = await self._sdk.images.edit(**kwargs)
        try:
            async for event in stream:
                yield _translate_stream_event(event)
        except Exception as e:  # noqa: BLE001
            yield StreamEvent(kind="error", error=str(e))


# -----------------------------------------------------------------------------
# Kwargs construction
# -----------------------------------------------------------------------------


def _generation_kwargs(req: GenerationRequest) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "model": req.model,
        "prompt": req.prompt,
        "n": req.n,
    }
    if req.size:               kwargs["size"] = req.size
    if req.quality:            kwargs["quality"] = req.quality
    if req.output_format:      kwargs["output_format"] = req.output_format
    if req.output_compression is not None:
        kwargs["output_compression"] = req.output_compression
    if req.background:         kwargs["background"] = req.background
    if req.moderation:         kwargs["moderation"] = req.moderation
    # response_format intentionally omitted: rejected by gpt-image with
    # "Unknown parameter: 'response_format'" — DALL-E-only.
    return kwargs


def _edit_kwargs(
    req: EditRequest, images: list[IO[bytes] | None], mask: IO[bytes] | None
) -> dict[str, Any]:
    # SDK accepts a single file or a list; always pass a list for uniform shape.
    image_arg: Any = [im for im in images if im is not None]
    if len(image_arg) == 1:
        image_arg = image_arg[0]
    kwargs: dict[str, Any] = {
        "model": req.model,
        "prompt": req.prompt,
        "image": image_arg,
        "n": req.n,
    }
    if mask is not None:        kwargs["mask"] = mask
    if req.size:                kwargs["size"] = req.size
    if req.quality:             kwargs["quality"] = req.quality
    if req.output_format:       kwargs["output_format"] = req.output_format
    if req.output_compression is not None:
        kwargs["output_compression"] = req.output_compression
    if req.input_fidelity:      kwargs["input_fidelity"] = req.input_fidelity
    if req.moderation:          kwargs["moderation"] = req.moderation
    # response_format intentionally omitted (DALL-E-only; rejected by gpt-image).
    return kwargs


# -----------------------------------------------------------------------------
# Response normalization
# -----------------------------------------------------------------------------


def _normalize(sdk_response: Any, *, model: ModelId, request_ms: int) -> ImageResponse:
    """Convert the SDK's response object to our :class:`ImageResponse`.

    Handles both the dict-shaped responses (older SDK) and the pydantic
    model-shaped responses (newer SDK) by going through ``model_dump``
    when available.
    """
    payload = (
        sdk_response.model_dump()
        if hasattr(sdk_response, "model_dump")
        else dict(sdk_response)
    )
    images_raw = payload.get("data") or []
    images = [
        ImageData(
            b64_json=item.get("b64_json"),
            url=item.get("url"),
            revised_prompt=item.get("revised_prompt"),
        )
        for item in images_raw
    ]
    usage_raw = payload.get("usage") or {}
    usage = ApiUsage(
        input_tokens=int(usage_raw.get("input_tokens", 0)),
        output_tokens=int(usage_raw.get("output_tokens", 0)),
        total_tokens=int(usage_raw.get("total_tokens", 0)),
        input_text_tokens=int(usage_raw.get("input_tokens_details", {}).get("text_tokens", 0))
            if isinstance(usage_raw.get("input_tokens_details"), dict)
            else 0,
        input_image_tokens=int(usage_raw.get("input_tokens_details", {}).get("image_tokens", 0))
            if isinstance(usage_raw.get("input_tokens_details"), dict)
            else 0,
    )
    return ImageResponse(
        images=images, usage=usage, model=model, request_ms=request_ms
    )


def _translate_stream_event(event: Any) -> StreamEvent:
    """Map the SDK's streaming event object to our :class:`StreamEvent`."""
    payload = event.model_dump() if hasattr(event, "model_dump") else dict(event)
    kind = payload.get("type", "completed")
    if kind in {"image.generation.partial_image", "image.edit.partial_image", "partial_image"}:
        return StreamEvent(
            kind="partial",
            index=int(payload.get("partial_image_index", 0)),
            b64_json=payload.get("b64_json") or payload.get("image", {}).get("b64_json"),
            revised_prompt=payload.get("revised_prompt"),
        )
    if kind in {"image.generation.completed", "image.edit.completed", "completed"}:
        usage_raw = payload.get("usage") or {}
        usage = ApiUsage(
            input_tokens=int(usage_raw.get("input_tokens", 0)),
            output_tokens=int(usage_raw.get("output_tokens", 0)),
            total_tokens=int(usage_raw.get("total_tokens", 0)),
        )
        b64 = (
            payload.get("b64_json")
            or (payload.get("image") or {}).get("b64_json")
            or (payload.get("data") or [{}])[0].get("b64_json")
        )
        return StreamEvent(
            kind="completed",
            b64_json=b64,
            revised_prompt=payload.get("revised_prompt"),
            usage=usage,
        )
    return StreamEvent(kind="error", error=f"unknown stream event: {kind}")


# -----------------------------------------------------------------------------
# Error classifier — used by retry.with_retry
# -----------------------------------------------------------------------------


def _classify_openai_error(e: BaseException) -> tuple[bool, int | None, float | None]:
    """Return (is_retriable, status, retry_after_s) for an OpenAI SDK error.

    Lazy-imports the SDK error types so this module remains import-safe
    when the SDK isn't installed (e.g., during certain unit-test runs
    that don't exercise the client).
    """
    try:
        from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, RateLimitError
    except ImportError:  # pragma: no cover
        return (False, None, None)

    if isinstance(e, RateLimitError):
        return (True, 429, _retry_after_from_error(e))
    if isinstance(e, APITimeoutError):
        return (True, None, None)
    if isinstance(e, APIConnectionError):
        return (True, None, None)
    if isinstance(e, APIStatusError):
        status = getattr(e, "status_code", None)
        if status is None:
            return (False, None, None)
        return (retry.is_retriable(status), status, _retry_after_from_error(e))
    if isinstance(e, APIError):
        return (False, None, None)
    return (False, None, None)


def _retry_after_from_error(e: BaseException) -> float | None:
    """Extract a Retry-After header from an OpenAI error if present."""
    response = getattr(e, "response", None)
    if response is None:
        return None
    headers = getattr(response, "headers", None) or {}
    if not headers:
        return None
    raw = headers.get("retry-after") or headers.get("Retry-After")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------


def _ms() -> int:
    return int(asyncio.get_event_loop().time() * 1000) if asyncio._get_running_loop() else 0


__all__ = [
    "ApiUsage",
    "AuthError",
    "EditRequest",
    "GenerationRequest",
    "ImageData",
    "ImageResponse",
    "InputTooLarge",
    "InvalidRequest",
    "ModerationBlocked",
    "OpenAIClientError",
    "OpenAIImageClient",
    "StreamEvent",
]
