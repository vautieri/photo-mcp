# =============================================================================
# photo-mcp — production image
# -----------------------------------------------------------------------------
# Multi-stage build:
#   1. builder  — installs build deps (gcc, libraw, etc.) and compiles wheels
#   2. runtime  — slim Python 3.12 + only the system libs the wheels need at
#                 runtime + the suite of CLI tools photographers reach for
#                 (darktable-cli, exiftool, libvips, imagemagick, gmic). The
#                 photographer can shell out to these from chat through the
#                 MCP host's BashTool when raw lossless edits are wanted.
# =============================================================================

ARG PYTHON_VERSION=3.12

# -----------------------------------------------------------------------------
# Stage 1: builder
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

# Build dependencies for rawpy, scikit-image, pillow, numpy.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        pkg-config \
        libraw-dev \
        liblcms2-dev \
        libjpeg-dev \
        zlib1g-dev \
        libtiff-dev \
        libpng-dev \
        libwebp-dev \
        libopenjp2-7-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Build a wheel + collect runtime deps as wheels into /wheels.
RUN python -m pip install --upgrade pip build \
    && python -m build --wheel --outdir /wheels \
    && pip wheel --wheel-dir /wheels '.[xmp]'

# -----------------------------------------------------------------------------
# Stage 2: runtime
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PHOTO_MCP_LOG_LEVEL=info

# Runtime libraries (no -dev) + the CLI darkroom suite.
# Why each tool ships in the runtime image:
#   darktable      — provides darktable-cli; the only RAW developer
#                    that respects camera profiles and ICCs without
#                    re-encoding to sRGB
#   exiftool       — read/write every metadata tag the embedded libs miss
#   libvips-tools  — fastest non-destructive resize / format convert
#   imagemagick    — universal swiss-army knife (composite, masks, etc.)
#   gmic           — high-quality denoise + tone curves
#   exempi         — XMP toolkit shared library (used by python-xmp-toolkit)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libraw20 \
        liblcms2-2 \
        libjpeg62-turbo \
        libtiff6 \
        libpng16-16 \
        libwebp7 \
        libopenjp2-7 \
        libexempi8 \
        darktable \
        libimage-exiftool-perl \
        libvips-tools \
        imagemagick \
        gmic \
        ca-certificates \
        tini \
    && rm -rf /var/lib/apt/lists/*

# Install the wheels we built in stage 1 (offline — no network).
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels photo-mcp \
    && rm -rf /wheels

# Non-root user — photo-mcp never needs root.
RUN groupadd --system --gid 1000 photo \
 && useradd  --system --uid 1000 --gid photo --create-home --shell /bin/bash photo

USER photo
WORKDIR /home/photo

# stdio is the MCP transport; tini reaps zombies and forwards signals.
ENTRYPOINT ["/usr/bin/tini", "--", "python", "-m", "photo_mcp"]
