"""OoT Randomizer's own hint texts, taken from its builders without patching a ROM.

OoTR's Hints.build_* functions write N64 messages through Messages.update_message_by_id and wrap lines for the N64
font (TextBox.line_wrap) on the way. capture() runs a builder with both swapped out for that call, so the messages
get collected as {message id: text} and nothing is wrapped (the remake wraps for its own boxes, _hints_text.wrap).
The vendored files aren't changed.
"""
import contextlib


@contextlib.contextmanager
def _captured(out):
    import Hints
    import Messages

    def update(messages, id, text, lang, opts=None, allow_duplicates=False, force_left=False,
               overwrite_existed=False):
        out[id] = text if isinstance(text, str) else bytes(text).decode("latin-1")
    saved = (Hints.update_message_by_id, Messages.update_message_by_id, Hints.line_wrap)
    Hints.update_message_by_id = Messages.update_message_by_id = update
    Hints.line_wrap = lambda text, *a, **k: text
    try:
        yield out
    finally:
        Hints.update_message_by_id, Messages.update_message_by_id, Hints.line_wrap = saved


def capture(fn, *args, **kwargs):
    """{message id: text} an OoTR text builder writes, unwrapped."""
    out = {}
    with _captured(out):
        fn(*args, **kwargs)
    return out


def unwrapped(fn, *args, **kwargs):
    """The return value of an OoTR string builder (build_boss_string, build_bridge_reqs_string...), unwrapped."""
    with _captured({}):
        return fn(*args, **kwargs)


def item_text(item_name, world, clearer=None):
    """OoTR's hint name for an item (clear or vague as clearer_hints says), as its misc hints write it."""
    from HintList import get_hint
    if clearer is None:
        clearer = world.settings.clearer_hints
    return get_hint(item_name, world.language, clearer).text


def generic_item_name(item):
    from Hints import get_item_generic_name
    return get_item_generic_name(item)


def area_of(spot, world, preposition=False, use_alt_hint=False):
    """(OoTR HintArea, its English text with '#' marks) for a location or region."""
    from Hints import HintArea
    area = HintArea.at(spot, use_alt_hint=use_alt_hint)
    return area, area.text(world.language, world.settings.clearer_hints, preposition=preposition)
