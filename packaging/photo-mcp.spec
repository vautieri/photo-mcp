# =============================================================================
# photo-mcp.spec — PyInstaller --onefile spec
#
# Produces a single photo-mcp.exe (or photo-mcp on Linux) that bundles:
#   * the photo_mcp package itself
#   * Pillow + pillow-heif (and its bundled libheif native blob)
#   * rawpy (and its bundled libraw native blob)
#   * openai client
#   * mcp / pydantic / httpx
#
# Native-lib gotchas:
#   - rawpy ships libraw as a compiled extension. PyInstaller's hook for it
#     is partial; `--collect-all rawpy` plus the explicit `binaries` entry
#     below catches the ones the hook misses.
#   - pillow-heif's binary wheel includes libheif + libde265 statically on
#     Windows, so `collect_all('pillow_heif')` is sufficient there. On Linux
#     PyPI wheels are manylinux and ship their .so files via auditwheel.
#
# Cross-platform note: this spec is platform-agnostic. PyInstaller produces
# a binary for the host OS — running this on Windows yields photo-mcp.exe,
# on Linux yields ./photo-mcp. The Windows CI runner is the source of
# truth for the .exe that ships in the installer.
#
# Invoke:    pyinstaller --clean --noconfirm packaging/photo-mcp.spec
# Output:    dist/photo-mcp.exe   (or dist/photo-mcp on POSIX)
# =============================================================================

# pylint: disable=undefined-variable    # PyInstaller injects names at runtime

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

# --- Heavy native deps: pull EVERYTHING (modules, data, binaries) ----------
_rawpy_datas,        _rawpy_bins,        _rawpy_hidden        = collect_all("rawpy")
_pillow_heif_datas,  _pillow_heif_bins,  _pillow_heif_hidden  = collect_all("pillow_heif")
_pillow_datas,       _pillow_bins,       _pillow_hidden       = collect_all("PIL")
_openai_datas,       _openai_bins,       _openai_hidden       = collect_all("openai")
_mcp_datas,          _mcp_bins,          _mcp_hidden          = collect_all("mcp")
_pydantic_datas,     _pydantic_bins,     _pydantic_hidden     = collect_all("pydantic")
_anyio_datas,        _anyio_bins,        _anyio_hidden        = collect_all("anyio")
_httpx_datas,        _httpx_bins,        _httpx_hidden        = collect_all("httpx")

hidden = (
    _rawpy_hidden
    + _pillow_heif_hidden
    + _pillow_hidden
    + _openai_hidden
    + _mcp_hidden
    + _pydantic_hidden
    + _anyio_hidden
    + _httpx_hidden
    + collect_submodules("photo_mcp")
    + [
        # belt-and-suspenders for tokenizer / encoder paths that openai
        # pulls in lazily
        "tiktoken_ext",
        "tiktoken_ext.openai_public",
    ]
)

datas = (
    _rawpy_datas
    + _pillow_heif_datas
    + _pillow_datas
    + _openai_datas
    + _mcp_datas
    + _pydantic_datas
    + _anyio_datas
    + _httpx_datas
    + [
        # photo_mcp's prices.json — bundled package data
        ("../src/photo_mcp/prices.json", "photo_mcp"),
    ]
)

binaries = (
    _rawpy_bins
    + _pillow_heif_bins
    + _pillow_bins
    + _openai_bins
)

a = Analysis(
    ["../src/photo_mcp/main.py"],
    pathex=["../src"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # heavy and unused — keep the .exe under 200 MB
        "tkinter",
        "matplotlib",
        "scipy",
        "pandas",
        "IPython",
        "jupyter",
        "pytest",
        "vcr",
        "freezegun",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="photo-mcp",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,           # UPX trips SmartScreen even harder than unsigned
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,        # MCP servers speak JSON-RPC on stdio
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
