# Sponsor Review Guide

**For**: the photographer (project sponsor)
**Purpose**: surface every design decision where your input changes what gets built. If you skip everything else and read only one doc, this is the one.

---

## How to use this

Each section below names one decision baked into the design. For each:

- **Default** → what I've already chosen on your behalf
- **Why** → the reasoning
- **Tweakable?** → can be changed without large rework
- **Your call** → the question I'm asking you

Mark anywhere you want a different choice. We'll revise the affected docs
and re-baseline before the implementation phase begins.

---

## A. Workflow defaults

### A.1 — Default model when you don't specify

**Default**: `gpt-image-2` for edits, `gpt-image-1.5` for prompt-only generations
**Why**: gpt-image-2 is highest fidelity and is the right default for editing your originals. For pure generation (no source), 1.5 is the price/quality sweet spot.
**Tweakable?** Yes (one-line config change).
**Your call**: Are these the right defaults? Or do you want gpt-image-2 everywhere, accepting the higher cost?

### A.2 — Default output format

**Default**: PNG (lossless)
**Why**: Photographers consistently say "don't compress my output." PNG is lossless, large but truthful. JPEG and WebP are available when you ask.
**Tweakable?** Yes (per call).
**Your call**: PNG default OK?

### A.3 — Default `preserve_metadata` flag

**Default**: `true` for edits and composites
**Why**: Your copyright, GPS, lens info should follow the image unless you specifically want it stripped.
**Tweakable?** Yes (per call).
**Your call**: Confirm — keep `true` as default?

### A.4 — Default `preserve_color_profile` flag

**Default**: `true` for edits and composites
**Why**: If you shoot AdobeRGB or ProPhoto, OpenAI returns sRGB and your gamut is silently shrunk. With `true`, the server embeds your source ICC profile in the output PNG so a color-managed app sees the right space.
**Tweakable?** Yes (per call).
**Your call**: Confirm `true` default?

### A.5 — Default `input_fidelity` for gpt-image-1.x edits

**Default**: `high`
**Why**: Photographers reported `low` ruined identity-preserving edits. High is the safer default; you can opt into `low` per call when you want a creative reinterpretation.
**Tweakable?** Yes (per call).
**Your call**: Confirm `high` default?

---

## B. Cost controls

### B.1 — Per-session cost ceiling

**Default**: unlimited (no ceiling)
**Why**: I don't want to invent a number for you. But running a long agent loop with no ceiling is a real way to spend $50–$200 unintentionally.
**Tweakable?** Yes (env var or per-call).
**Your call**: What's the most you'd want to spend in one continuous session before the server pauses and asks? My suggestion: **$10**, but tell me what fits your workflow.

### B.2 — Estimate accuracy target

**Default**: ±2% of OpenAI's billed cost, validated by the V&V live-API run.
**Why**: Tight enough that you can trust the estimate; loose enough that price-table updates lag a few days.
**Tweakable?** Yes.
**Your call**: ±2% acceptable, or do you want tighter / looser?

---

## C. Workflow scope

### C.1 — RAW handling

**Default**: Server pre-converts RAW (`.cr3`, `.nef`, `.arw`, `.dng`, etc.) to PNG via `rawpy` before upload, with photographer-controllable de-bayer parameters (camera matrix, no auto-bright, 16-bit by default).
**Why**: OpenAI doesn't accept RAW. Conversion has to happen somewhere. Doing it in the server gives you control over the conversion parameters (`raw_params` in tool input).
**Tweakable?** Yes — you can pre-convert in Lightroom/Capture One yourself and just hand the server a TIFF/PNG.
**Your call**: (a) you want server-side RAW conversion as a one-stop shop, or (b) you'd rather convert in your existing tool and skip RAW support entirely?

### C.2 — Iterative-edit warning threshold

**Default**: SSIM < 0.92 cumulative drop triggers a warning in the tool result.
**Why**: Users complained AI iterations devolve into "globs". A warning protects you without preventing the operation.
**Tweakable?** Yes (config value).
**Your call**: Right threshold? Lower = warns sooner. My suggestion: 0.92 first warn, 0.85 hard refuse-unless-confirm.

### C.3 — Output filename collision behavior

**Default**: Refuse with an explicit error unless `overwrite=true` is set.
**Why**: Easy to lose 4 hours of editing by overwriting yesterday's good output. Refusing by default is the safer pose.
**Tweakable?** Yes (per call).
**Your call**: Confirm refusal default?

### C.4 — Multi-image edits — which photo's metadata is preserved

**Default**: `image[0]` (the first one in your list)
**Why**: When 16 input photos collapse to one output, only one set of metadata can survive. First-in-list is the convention; you can override per call by reordering.
**Tweakable?** Yes (per call).
**Your call**: Confirm "first input is metadata source"?

---

## D. Reference photo set

### D.1 — Pick 10 photos that represent your real work

**Default**: I'll pick reasonable rendered substitutes if you don't supply.
**Why**: SSIM and EXIF tests run against this set. Tests pass on these → confidence the software handles real shoots.
**Tweakable?** Yes — you can swap photos at any time; tests re-run.
**Your call**: Send me 10 photos covering:

- 1× studio portrait, sRGB, full EXIF
- 1× natural-light portrait (RAW from your usual body)
- 1× landscape (any camera, any RAW or post-processed)
- 1× low-light / high-ISO
- 1× product / commercial work, transparent background opportunity
- 1× a photo with GPS + Copyright + IPTC fields filled (for round-trip tests)
- 1× a "tough" photo — fine detail / hair / fabric texture you've seen AI mangle before
- 3× whatever else you think will trip it up

If you'd rather I pick from public-domain reference photos, say so. **Your originals never leave your machine** — fixtures live locally on the dev machine and only synthesized files go in the public repo.

---

## E. Deployment

### E.1 — Where the server runs

**Default**: Your workstation (Windows or Linux), invoked by an MCP-aware
client (Claude Desktop, ChatGPT Desktop, custom CLI). stdio mode.
**Why**: Your photos and API key stay local. No cloud; nothing to host.
**Tweakable?** Yes — HTTP+SSE mode is also built so you could run it on a home server and call it from a different machine.
**Your call**: stdio (workstation-local) sufficient, or do you want HTTP+SSE for a multi-machine setup?

### E.2 — macOS

**Default**: Deferred to v1.1 (within +30 days of v1.0).
**Why**: Same code, same tests should work, but I want to verify rather than promise. Windows and Linux are the v1.0 commitment.
**Tweakable?** No (it's a date, not a feature).
**Your call**: Will you be using this on a Mac? If yes, when? If "not for the next month," current plan is fine.

---

## F. Things I'll just decide unless you object

These are decisions I'm not asking you about, but I'm listing them so you
know they were made:

1. **Language**: Python 3.12. Best image library ecosystem; cross-platform; PyInstaller produces single-file Windows + Linux binaries.
2. **Distribution**: PyPI wheel + standalone single-file executable per OS.
3. **Logging**: JSON-line to stderr; never to stdout (stdout is the MCP protocol channel).
4. **Test framework**: pytest + vcrpy cassettes for repeatable replays.
5. **Source code repo**: at `/mnt/f/cl/mcp/photo-mcp/`. Git, with the same place reserved for future MCP servers under `/mnt/f/cl/mcp/`.

If any of these matter to you, flag them and we discuss.

---

## G. What approval looks like

When you're ready:

1. Read this doc and the executive summary (`00-executive-summary.md`).
2. Skim the requirements (`02-requirements.md`) and risk register (`08-risk-register.md`); flag anything that doesn't match what you want.
3. Tell me your answers / concerns for sections A through E above. (Section F you can ignore unless something jumps out.)
4. I revise the affected docs.
5. You sign off in `01-project-charter.md` (just the §9 block; can be "approved on `<date>` via this commit / message").
6. Implementation begins.

No implementation work begins until §G.5 is done.

---

## Quick-decision shortlist

If you want to give me direction in 5 minutes, just answer these:

1. Per-session cost ceiling (USD): __________
2. RAW conversion in the server (yes / no / I'll pre-convert): __________
3. Will you use this on a Mac in the next 30 days? (yes / no): __________
4. Send 10 reference photos (yes, will send / use rendered substitutes): __________
5. Anything in the design that's wrong / missing? (free text): __________

Everything else is fine with the documented defaults.
