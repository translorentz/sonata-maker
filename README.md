# Sonata Maker

Generate piano sonata-form movements from LilyPond motifs using AI. Produces
a complete score (PDF), MIDI, audio (WAV), and video (MP4) from a short
musical motif.

## How it works

1. A LilyPond motif snippet is sent to an OpenAI reasoning model with a
   detailed composition rubric (sonata form, texture diversity, etc.)
2. The generated LilyPond source is compiled; compilation errors are
   automatically repaired via a second LLM call
3. MIDI velocity balancing adjusts LH/RH volume for a natural piano sound
4. FluidSynth renders the MIDI to audio using a SoundFont
5. The PDF score is converted to PNG pages and assembled into a contact sheet
6. FFmpeg combines the contact sheet and audio into a still-image MP4

## Requirements

### Python

- Python >= 3.10
- Dependencies: `openai`, `mido`

### External tools (must be on PATH)

| Tool         | Purpose              | Install                              |
|--------------|----------------------|--------------------------------------|
| `lilypond`   | Music engraving      | https://lilypond.org                 |
| `fluidsynth` | MIDI -> WAV          | `brew install fluidsynth`            |
| `pdftoppm`   | PDF -> PNG           | `brew install poppler`               |
| `magick`     | Contact sheet        | `brew install imagemagick`           |
| `ffmpeg`     | Video encoding       | `brew install ffmpeg`                |

### Environment

```sh
export OPENAI_API_KEY="sk-..."
export SOUNDFONT_PATH="/path/to/soundfont.sf2"   # optional, or use --soundfont
```

## Installation

```sh
pip install -e .
```

For development:

```sh
pip install -e ".[dev]"
```

## Usage

```sh
# Using the installed command
sonata-maker examples/motif.ly -o build_out --name sonata_01 --title "Sonata in G"

# Or via python -m
python -m sonata_maker examples/motif.ly -o build_out --name sonata_01 --verbose

# Adjust MIDI balance
sonata-maker examples/motif.ly --lh-scale 0.75 --rh-scale 1.08

# Skip MIDI balancing entirely
sonata-maker examples/motif.ly --no-midi-balance
```

### Key options

| Flag                  | Default       | Description                                 |
|-----------------------|---------------|---------------------------------------------|
| `--out`, `-o`         | `out_sonata`  | Output directory                            |
| `--name`              | `sonata`      | Base filename for all outputs               |
| `--title`             | (from --name) | Score title in the PDF header               |
| `--soundfont`         | `$SOUNDFONT_PATH` | Path to a `.sf2` SoundFont             |
| `--verbose`           | off           | Stream external tool output                 |
| `--no-midi-balance`   | off           | Skip LH/RH velocity adjustment             |
| `--lh-scale`          | `0.78`        | LH velocity multiplier (lower = softer)     |
| `--rh-scale`          | `1.05`        | RH velocity multiplier (higher = louder)    |
| `--fluidsynth-gain`   | `0.7`         | Global FluidSynth gain                      |
| `--model`             | `gpt-5.1`    | OpenAI model to use                         |
| `--reasoning`         | `high`        | Reasoning effort level                      |
| `--dpi`               | `300`         | PNG render resolution                       |

### Outputs

For `--name sonata_01`:

| File                      | Description                    |
|---------------------------|--------------------------------|
| `sonata_01.ly`            | Generated LilyPond source      |
| `sonata_01.pdf`           | Engraved score                 |
| `sonata_01.midi`          | Raw MIDI from LilyPond         |
| `sonata_01_mix.midi`      | Velocity-balanced MIDI         |
| `sonata_01.wav`           | Rendered audio                 |
| `sonata_01.mp4`           | Score video with audio         |
| `sonata_01_contact.png`   | Contact sheet of score pages   |

## Testing

```sh
pytest
```

## Project structure

```
src/sonata_maker/
  __init__.py       Package root
  __main__.py       python -m entry point
  cli.py            Argument parsing and main()
  config.py         ToolPaths and RenderConfig dataclasses
  errors.py         Custom exceptions
  generate.py       OpenAI generation and repair
  lilypond.py       LilyPond source validation and compilation
  midi.py           MIDI velocity balancing
  motif.py          Motif key/time extraction
  output.py         Logging and progress output
  pipeline.py       End-to-end orchestration
  prompts.py        LLM prompt templates
  render.py         fluidsynth, pdftoppm, magick, ffmpeg wrappers
  tools.py          Tool discovery and subprocess helpers
```
