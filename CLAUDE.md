# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build and test commands

```sh
# Setup: create venv and install (first time)
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Run all tests
.venv/bin/pytest

# Run a single test file or test
.venv/bin/pytest tests/test_lilypond.py
.venv/bin/pytest tests/test_lilypond.py::TestValidateLilypondSource::test_rejects_relative

# Run with coverage
.venv/bin/pytest --cov=sonata_maker

# Run the CLI
.venv/bin/sonata-maker examples/motif.ly --soundfont /path/to/sf2 -o build_out --name sonata_01
.venv/bin/python -m sonata_maker examples/motif.ly --soundfont /path/to/sf2
```

There is no linter configured. The project uses `pyproject.toml` with Hatch as the build backend.

## Architecture

This is an 8-step pipeline that takes a LilyPond motif snippet and produces a score video (PDF, MIDI, WAV, MP4). The pipeline has two distinct halves: **AI generation** (steps 1-2) and **deterministic rendering** (steps 3-8).

### Pipeline flow (orchestrated by `pipeline.build_outputs`)

```
motif.ly → [OpenAI] → .ly source → [LilyPond] → .pdf + .midi
                           ↑                          ↓
                    [auto-repair loop]          [MIDI balance]
                                                      ↓
                                              .midi → [fluidsynth] → .wav
                                              .pdf  → [pdftoppm]   → PNGs
                                              PNGs  → [magick]     → contact sheet
                                              sheet + wav → [ffmpeg] → .mp4
```

### Key design patterns

- **Auto-repair loop**: If LilyPond compilation fails, the pipeline sends the broken source + compiler stderr back to the LLM for repair (`generate.fix_sonata_lilypond`), retrying up to `max_compile_fix_attempts` times. This loop lives in `pipeline.build_outputs`.

- **External tool abstraction**: All 5 CLI tools (lilypond, fluidsynth, pdftoppm, magick, ffmpeg) are discovered at startup via `tools.discover_tool_paths` and stored in a frozen `ToolPaths` dataclass. Every rendering function takes `ToolPaths` as its first argument rather than hardcoding tool names.

- **Two config dataclasses** (`config.py`): `ToolPaths` for resolved binary paths, `RenderConfig` for tunable pipeline parameters (model, DPI, sample rate, retry counts, etc.). Both are frozen.

- **LilyPond source validation** (`lilypond.validate_lilypond_source`): Structural checks (absolute pitch mode, required blocks) run before and after LLM generation. The `sanitize_model_output` step strips markdown fences that LLMs tend to emit.

- **MIDI velocity balancing** (`midi.py`): Heuristically identifies LH/RH channels by pitch distribution (split at middle C = MIDI note 60), then scales velocities independently to fix typical LilyPond MIDI loudness imbalance.

### Module dependency graph

```
cli → pipeline → generate → prompts, lilypond, motif
                → lilypond (compile)
                → midi
                → render (fluidsynth, pdftoppm, magick, ffmpeg)
                → tools

All modules use: config (dataclasses), errors, output (logging)
```

The `output` module (not `logging`) provides `log()`, `banner()`, and `StepTimer`. It's named `output` to avoid shadowing stdlib `logging`.

### OpenAI API usage

`generate.py` uses the **Responses API** (`client.responses.create`) with `reasoning={"effort": ...}`. The prompts in `prompts.py` are extensive composition rubrics enforcing sonata form, texture diversity, and LilyPond engraving constraints. The system prompt is ~4K tokens.

### Environment requirements

- `OPENAI_API_KEY` must be set for generation
- `SOUNDFONT_PATH` (optional) or `--soundfont` flag for audio rendering
- Five external CLI tools must be on PATH: `lilypond`, `fluidsynth`, `pdftoppm` (poppler), `magick` (ImageMagick), `ffmpeg`

### Testing approach

Tests cover pure-logic modules only (motif parsing, LilyPond validation/header injection, basename validation, config dataclasses, CLI arg parsing, MIDI channel guessing). Tests for MIDI use `unittest.mock` to avoid requiring actual MIDI files. No tests require external tools or API keys.
