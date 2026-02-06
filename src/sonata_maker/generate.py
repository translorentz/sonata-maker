"""OpenAI-powered LilyPond generation and compilation repair."""

from __future__ import annotations

from typing import Optional

from openai import OpenAI

from sonata_maker.config import RenderConfig
from sonata_maker.errors import SonataGenerationError
from sonata_maker.lilypond import (
    inject_or_update_header,
    sanitize_model_output,
    validate_lilypond_source,
)
from sonata_maker.motif import extract_key_and_time
from sonata_maker.output import banner, log, StepTimer
from sonata_maker.prompts import (
    FIX_PROMPT_TEMPLATE,
    SYSTEM_PROMPT,
    USER_PROMPT_TEMPLATE,
)


def generate_sonata_lilypond(
    client: OpenAI,
    motif_text: str,
    title: str,
    cfg: RenderConfig,
) -> str:
    """Generate a complete sonata-form LilyPond file from a motif snippet.

    Retries up to cfg.max_generation_attempts times on validation failure.
    """
    key_desc, time_sig = extract_key_and_time(motif_text)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        motif=motif_text.strip(),
        key_desc=key_desc,
        time_sig=time_sig,
        title=title.strip(),
    )

    last_err: Optional[Exception] = None
    for attempt in range(1, cfg.max_generation_attempts + 1):
        banner(
            f"[1/8] Generating LilyPond sonata with {cfg.model} "
            f"(attempt {attempt})"
        )
        try:
            with StepTimer("OpenAI request (may take a while)"):
                resp = client.responses.create(
                    model=cfg.model,
                    reasoning={"effort": cfg.reasoning_effort},
                    input=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
            ly = sanitize_model_output(resp.output_text)
            ly = inject_or_update_header(ly, title=title)
            validate_lilypond_source(ly)
            return ly
        except Exception as e:
            last_err = e
            log(f"[WARN] Generation attempt {attempt} failed: {e}")

    raise SonataGenerationError(
        f"Failed to generate valid LilyPond. Last error: {last_err}"
    )


def fix_sonata_lilypond(
    client: OpenAI,
    broken_code: str,
    lilypond_cmd: list[str],
    lilypond_stderr: str,
    title: str,
    cfg: RenderConfig,
) -> str:
    """Ask the model to repair a broken LilyPond file using compiler errors."""
    excerpt = lilypond_stderr.strip()
    if len(excerpt) > 4000:
        excerpt = excerpt[-4000:]

    fix_prompt = FIX_PROMPT_TEMPLATE.format(
        cmd=" ".join(lilypond_cmd),
        stderr=excerpt,
        code=broken_code,
    )

    banner("[X] LilyPond failed; asking model to repair the full file")
    with StepTimer("OpenAI repair request (may take a while)"):
        resp = client.responses.create(
            model=cfg.model,
            reasoning={"effort": cfg.reasoning_effort},
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": fix_prompt},
            ],
        )

    ly = sanitize_model_output(resp.output_text)
    ly = inject_or_update_header(ly, title=title)
    validate_lilypond_source(ly)
    return ly
