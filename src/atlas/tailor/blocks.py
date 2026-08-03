"""Map AI tailoring decisions back onto master-resume blocks (PROJECT.md §5.7).

Pure, I/O-free glue between the AI's :class:`~atlas.tailor.structure.TailoredResume`
and the render pipeline. :func:`tag_blocks_for_prompt` renders the source blocks
with their ``content_id``s so the model can reference them; :func:`render_blocks`
maps the model's returned items *back* onto the real source blocks **by
content_id** — dropping any id the model invented (a truth-anchoring guard) and any
item it marked excluded — and substitutes the tailored text. The result is a list
of unpersisted :class:`~atlas.db.models.ResumeBlock` instances that
:func:`atlas.render.build_resume_context` already accepts, so the tailored subset
renders through the exact same theme path as the master resume.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from atlas.db.models import ResumeBlock

if TYPE_CHECKING:
    from atlas.tailor.structure import TailoredItem

__all__ = ["render_blocks", "tag_blocks_for_prompt"]


def tag_blocks_for_prompt(blocks: list[ResumeBlock]) -> str:
    """Render ``blocks`` as a content-ID-tagged plaintext list for the prompt.

    Each block becomes a ``[content_id] (type) text`` line so the model can
    select and reword by id without inventing new content.
    """
    lines: list[str] = []
    for block in blocks:
        text = " ".join(block.text.split())
        lines.append(f"[{block.content_id}] ({block.type}) {text}")
    return "\n".join(lines)


def render_blocks(items: list[TailoredItem], source_blocks: list[ResumeBlock]) -> list[ResumeBlock]:
    """Map included ``items`` onto ``source_blocks`` by content id, tailored text applied.

    Args:
        items: The AI's per-block decisions (in intended display order).
        source_blocks: The master-resume version's blocks (the source of truth).

    Returns:
        Unpersisted :class:`~atlas.db.models.ResumeBlock` instances — one per
        included item whose ``content_id`` matches a real source block — carrying
        the source block's ``type``/``content_id`` but the tailored ``final_text``.
        Items with an unknown id or ``included=False`` are dropped. Order follows
        ``items`` (the AI's chosen ordering), not the source order.
    """
    by_id = {block.content_id: block for block in source_blocks}
    tailored: list[ResumeBlock] = []
    for position, item in enumerate(items):
        if not item.included:
            continue
        source = by_id.get(item.content_id)
        if source is None:
            # The model referenced an id not in the master resume — drop it rather
            # than emit unsupported content (truth-anchoring guard, §11).
            continue
        text = item.final_text.strip() or source.text
        tailored.append(
            ResumeBlock(
                master_resume_id=source.master_resume_id,
                type=source.type,
                content_id=source.content_id,
                position=position,
                text=text,
                tags=dict(source.tags),
            )
        )
    return tailored
