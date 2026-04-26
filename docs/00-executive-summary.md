# photo-mcp — Executive Summary

**For**: the photographer (project sponsor)
**By**: lead engineer
**Date**: 2026-04-25
**Read time**: ~5 minutes

---

## What is this?

A small program that runs quietly on your computer and lets your AI assistant
(Claude, ChatGPT Desktop, etc.) work directly with OpenAI's image models —
**gpt-image-1**, **gpt-image-1.5**, and the new **gpt-image-2** — using
**your own photographs** as the starting point.

It is built specifically for **professional photography** rather than general
hobbyist use. That means:

1. **Your originals stay original.** Nothing is silently resized, recompressed,
   or color-shifted. If a transformation would lose detail, the program tells
   you and asks if you want it.

2. **Your metadata follows the image.** Copyright, camera, lens, GPS, IPTC
   credits — all the things you (or Lightroom / Capture One) put on the file
   — get re-attached to whatever the AI hands back. OpenAI's API strips them;
   this server puts them back.

3. **You see how much the AI changed.** When you ask for an edit, the result
   comes with an "SSIM" number — a pixel-level similarity score. 1.00 means
   identical, 0.95+ means "the edit you asked for, nothing else." If a tool
   call ever drops below that, you'll see it.

4. **You pick the model.** gpt-image-2 is the highest-quality and the only
   one that does 4K, but it doesn't do transparent backgrounds and it
   forces "preserve the source faithfully" — not always what you want for
   creative reinterpretations. gpt-image-1.5 is the price/quality sweet
   spot for most editing. gpt-image-1 / 1-mini are the cheap options for
   prompt-only ideation. The server lets you pick per call.

5. **You see the cost before and after.** Every call returns the dollar
   estimate; you can set a session ceiling and the server refuses calls
   past it.

---

## What it is not

- It is not Photoshop. No auto-tone, no auto-sharpen, no denoise.
- It is not a plugin for Lightroom / Capture One. (Those would be separate
  projects; the MCP server can be called from any tool that speaks MCP.)
- It is not a cloud service. Runs locally; your photos and your API key
  never leave your machine except to go to OpenAI for the actual generation.
- It does not store or upload your images anywhere besides the OpenAI API
  call itself.

---

## What the server is capable of (these are tested examples, not your menu)

The list below is what the server is **verified to handle**. They're named
acceptance examples — not a constrained list of allowed workflows. You
can ask the server in plain English for anything that uses these
capabilities (or combinations of them). If a category below passes its
test, anything within that category works, not just the specific
example shown.

### 1. **Sky replacement, atmosphere, rainbows — by typing what you want**

Instead of buying overlay packs, sliders, and brushes:

> "Replace this overcast sky with golden-hour cumulus, keep the foreground
> exactly as-is, match the warm light onto the existing scene."

> "Add a subtle rainbow arching from the left tree to the lake, leave
> everything else untouched."

→ Your photo, transformed. Foreground SSIM ≥ 0.95 (tested). Camera/lens/
copyright metadata preserved. Provenance sidecar written.

### 2. **Two-photo merge** — sky from one shot, foreground from another

> "Use the sky from image 1, the foreground from image 2, blend the
> lighting so the merge looks like a single capture."

→ One coherent frame. The first photo's metadata is what survives. The
sidecar lists both source files with their SHA-256 hashes so any future
viewer can verify the lineage.

### 3. **Three-photo merge** — pose / subject / location combinations

> "Model from image 1, pose from image 2, dropped into the location of
> image 3, matching shadows to the location's light direction."

→ One frame. All three sources are recorded in the sidecar. Up to 16
inputs supported if you ever need that many references.

### 4. **"Put this dress on this person"** — wardrobe / product on a subject

> Two photos: a person, a clothing reference. "Replace what they're
> wearing with the garment in image 2, match the lighting and pose."

→ One photo. Identity preserved (face-region SSIM ≥ 0.92 tested).

### 5. **Color/mood shifts without composition change**

> "Twilight mood, slightly cooler shadows, warmer highlights. Don't
> change the composition."

→ Same shot, mood-shifted. Output dimensions identical to source. Sidecar
documents the prompt so you can repeat (or refine) the recipe.

### 6. **Generate from words alone** (when you have no source)

> "Studio portrait of a woman in her 30s, soft window light, 85mm lens
> look, shallow depth of field, neutral background"

→ Fresh AI image, no source photo needed. Used for ideation / mood boards
/ mockups.

---

## Authenticity guarantee

Your originals never get touched. Every output the server creates lives at
a *new* path, and right next to it the server writes a small JSON file
(`yourphoto.png.photo-mcp.json`) containing:

- The exact path of every source photo you used
- The SHA-256 hash of each source (so years later you can prove the
  source file is the same one the sidecar references)
- The exact prompt you typed
- The model and every parameter
- The SSIM score (how much pixels changed)
- The dollar cost

If anyone ever asks "is this photo real or AI?", you can hand them the
sidecar and the original source file. They run a hash check and the
math proves it.

That is the literal "you could pull the original and see it's not fake"
requirement, made provable on disk.

---

## How long until I can use it?

Three phases:

1. **Design** (you're reading the result of this phase) — ~2 days
2. **Implementation + verification** (only after you approve the design) —
   ~2 weeks at sustainable pace
3. **You try it with your real workflow** — final acceptance

Total: ~3 weeks from your design approval. Faster is possible but the goal
is "works correctly the first time you try it on a real shoot," not "ships
fast."

---

## What I need from you

Three things. Detail in `docs/sponsor-review-guide.md`:

1. **Read the design** (this folder, `docs/01-…` through `08-…`). Skim the
   parts that interest you, ignore the parts that don't. Anything you
   want changed, mark it in the doc and we revise.

2. **Pick 10 reference photos** that represent your work. They become the
   test fixtures the software is verified against. If the software works
   on your 10 chosen photos, it'll work on your 11th.

3. **Set a per-session cost ceiling.** OpenAI charges per image. The
   server enforces a limit so a runaway loop can't spend $200. What's
   the most you'd want to spend in one continuous working session before
   the server pauses and asks?

---

## Risks to your eyes

Top risk: **gpt-image-2 doesn't let you ask for low-fidelity reinterpretation.**
It's always faithful. For "preserve my photo, edit only the cloud" workflows
that's a feature. For "give me a wild creative variation" workflows you'd
have to use gpt-image-1 or 1.5. The server lets you pick per call so you're
not locked in.

Second risk: **iteration degrades quality.** If you take an edited photo
and edit IT again, then again, OpenAI's models accumulate small artifacts.
The server reports SSIM after every edit so you can see the drift; we may
add a stronger warning if it drops past a threshold.

Third risk: **OpenAI ships breaking API changes.** They just released
gpt-image-2 (April 21, 2026). The server pins the SDK version and has tests
that catch drift, so when they next change something, we'll know within
hours, not weeks.

---

## Where this fits

```
   Your camera ──► your photos
                       │
                       ▼
              your photos go through
              your usual workflow
              (Lightroom, Capture One)
                       │
                       ▼
            for AI edits, send through
            ───► photo-mcp ◄──── instructions you type
                       │           via Claude / ChatGPT Desktop
                       ▼              or via MICHAEL — see below
                 OpenAI gpt-image-X
                       │
                       ▼
            edited photo, with your
            metadata preserved
                       │
                       ▼
                  back to you
```

Nothing in your existing workflow is replaced. The MCP server is a new tool
you can reach for when you want AI image work integrated into a chat-based
agent loop.

## Bonus: photo-mcp + MICHAEL = full integration

Because photo-mcp speaks the standard Model Context Protocol, **MICHAEL**
(the C++23 agent we've been building in the other project) can use it as
a registered MCP server with one config-file entry. The result:

```
You type natural language → MICHAEL → photo-mcp → OpenAI → your edited photo
```

MICHAEL's chat interface gets `generate`, `edit`, `list_models`,
`estimate_cost`, and `attach_metadata` next to its built-in tools.
You ask "compose the dress from `dress.png` onto the model in
`portrait.cr3`, output to `~/edits/`" and MICHAEL routes the call to
photo-mcp transparently — you never type a CLI flag.

Coordinator-mode workflows: ask MICHAEL to "process my entire shoot
folder, edit each photo per the brief in `~/brief.md`." MICHAEL spawns
sub-agents (one per photo); each sub-agent calls `photo-mcp.edit` with
its own context; each sub-agent's progress shows in MICHAEL's live agent
panel.

Setup is a 6-line addition to MICHAEL's `settings.json`. Full instructions:
`docs/integration-with-michael.md`.

---

## Where to read more

| Doc | Purpose | Read if you want to know… |
|---|---|---|
| `01-project-charter.md` | Goals, scope, success criteria | what "done" means |
| `02-requirements.md` | Every feature, every parameter | what each tool will do exactly |
| `03-wbs.md` | The work breakdown | what's being built and in what order |
| `04-cdrls.md` | The deliverables list | what artifacts you'll receive and when |
| `05-system-design.md` | The technical architecture | (skip unless you want the tech detail) |
| `06-vv-plan.md` | How we verify it works | how each feature is tested |
| `07-evm-baseline.md` | Schedule and progress tracking | how we'll report progress |
| `08-risk-register.md` | What could go wrong | the mitigations in place |
| `09-sponsor-review-guide.md` | **Your action items** | start here for what you should weigh in on |
| `10-process-flow.md` | The binding process (gates, parallelism rules, deviation rules, final attestation) | If you want to see how I'm forced to follow the plan I just laid out |

---

## How this gets built — the discipline

I bound myself to a written Process Flow (`docs/10-process-flow.md`)
that says:

- **Four gates, sequential**: Design → Implementation → Verification →
  Acceptance. No work in a phase begins until the previous phase's gate
  passes — and you (the sponsor) approve each gate.
- **Parallelism only where dependencies allow** — work that doesn't
  share files runs concurrently to compress schedule, never to skip a
  step.
- **No silent deviations** — every change to the plan is recorded in a
  deviation log that you approve.
- **Continuous audit trail** — every gate, every work-package start
  and finish, every deviation gets one line in `process-ledger.md`.
- **Final compliance attestation** — at delivery, I produce a written
  attestation that the process was followed without undeclared
  deviation; you verify it against your own observation, and only then
  is v1.0 declared done.

If at the end of the project I cannot honestly attest to following the
process, the project does not close. That's the binding bar.

---

## One-line summary

A locally-run, professional-photography-aware bridge between your AI assistant
and OpenAI's gpt-image models that **preserves source quality, source
metadata, source color profile**, **shows you exactly what changed**, and
is **built under a written process you approve at every gate**.
