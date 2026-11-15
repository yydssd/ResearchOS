"""The four defences (design §7.4).

Every path below is a way a plausible-looking model answer must be refused. The
distinction that matters: a *bad point* is dropped and the rest survives, a
*broken schema* rejects the whole answer - half a description is still useful,
half a quote is not.
"""

from __future__ import annotations

from research_os.domain.models import DocumentChunk
from research_os.llm.base import MethodDescriptionResponse, MethodPointDraft
from research_os.research.method_description import validate_description

CHUNK_TEXT = (
    "LangProp turns a language model's proposals into executable policies. "
    "Our method stores each policy as code and scores it by execution feedback. "
    "The gating mechanism decides which programs are reused."
)
CHUNKS = [
    DocumentChunk(id="chunk_0", source_version_id="sv_1", section="Method", chunk_index=0, text=CHUNK_TEXT)
]
GOOD_QUOTE = "Our method stores each policy as code and scores it by execution feedback."


def _draft(**overrides) -> MethodPointDraft:
    data = dict(
        aspect="mechanism",
        statement="Stores each policy as code for later reuse.",
        quote=GOOD_QUOTE,
        chunk_id="chunk_0",
        section="Method",
    )
    data.update(overrides)
    return MethodPointDraft(**data)


def _validate(*drafts: MethodPointDraft):
    return validate_description(MethodDescriptionResponse(points=list(drafts)), CHUNKS)


def test_a_locating_point_is_kept():
    outcome = _validate(_draft())

    assert outcome.reason is None
    assert len(outcome.points) == 1
    assert outcome.points[0].aspect == "mechanism"
    assert outcome.points[0].chunk_id == "chunk_0"


def test_a_quote_not_in_its_chunk_is_dropped():
    """The whole point of the layer: a statement without a source location is a
    summary, and plan §7.4 forbids storing those."""
    outcome = _validate(_draft(quote="Policies are compiled into a graph of skills"))

    assert outcome.points == []
    assert outcome.reason == "METHOD_POINT_UNLOCATABLE"


def test_a_short_quote_is_dropped():
    """`quote="attention"` would "locate" itself everywhere; four words is the
    smallest quote that still identifies one sentence."""
    outcome = _validate(_draft(quote="Our method"))

    assert outcome.points == []
    assert outcome.reason == "METHOD_POINT_UNLOCATABLE"


def test_a_quote_that_appears_twice_is_dropped():
    """Non-unique quotes do not locate: the reader cannot tell which occurrence
    the statement came from."""
    repeated = [
        DocumentChunk(
            id="chunk_0", source_version_id="sv_1", section="Method", chunk_index=0,
            text="The gating mechanism is reused. The gating mechanism is reused.",
        )
    ]
    outcome = validate_description(
        MethodDescriptionResponse(points=[_draft(quote="The gating mechanism is reused.")]), repeated
    )

    assert outcome.points == []
    assert outcome.reason == "METHOD_POINT_UNLOCATABLE"


def test_a_statement_with_no_word_from_its_quote_is_dropped():
    """Formally fine, substantively invented: a real quote with a statement
    about something else is the failure `METHOD_STATEMENT_UNSUPPORTED` names."""
    outcome = _validate(
        _draft(
            quote=GOOD_QUOTE,
            statement="The model is trained with a contrastive objective on video.",
        )
    )

    assert outcome.points == []
    assert outcome.reason == "METHOD_STATEMENT_UNSUPPORTED"


def test_a_broken_schema_rejects_every_point():
    """An out-of-enum aspect means the model did not follow the contract; keeping
    its other points would be trusting an answer we know is malformed."""
    outcome = _validate(_draft(), _draft(aspect="vibes"))

    assert outcome.points == []
    assert outcome.reason == "METHOD_DESCRIPTION_REJECTED"


def test_a_chunk_id_outside_the_input_is_a_rejection():
    outcome = _validate(_draft(chunk_id="chunk_999"))

    assert outcome.points == []
    assert outcome.reason == "METHOD_DESCRIPTION_REJECTED"


def test_one_bad_point_does_not_discard_the_good_one():
    outcome = _validate(_draft(), _draft(quote="This sentence is not in the chunk at all"))

    assert len(outcome.points) == 1
    assert outcome.reason == "METHOD_POINT_UNLOCATABLE"


def test_an_aspect_word_alone_does_not_support_a_statement():
    """"mechanism" is the schema's word, not the paper's: with it removed,
    "Mechanism decides reuse" shares only one content word with its quote."""
    quote = "The gating mechanism decides which programs are reused"
    outcome = _validate(_draft(quote=quote, statement="Mechanism decides reuse."))

    assert outcome.points == []
    assert outcome.reason == "METHOD_STATEMENT_UNSUPPORTED"


def test_a_quote_across_a_line_break_still_locates():
    """Chunks keep the source's line breaks; a model that answers with one space
    quotes the same text. Folding must apply to the uniqueness check too, or a
    correct quote is dropped for its whitespace."""
    wrapped = [
        DocumentChunk(
            id="chunk_0", source_version_id="sv_1", section="Method", chunk_index=0,
            text="We store each policy\nas code and score it by execution feedback.",
        )
    ]
    outcome = validate_description(
        MethodDescriptionResponse(
            points=[_draft(quote="We store each policy as code and score it by execution feedback.", statement="Stores each policy as code and scores it by execution feedback.")]
        ),
        wrapped,
    )

    assert len(outcome.points) == 1
    assert outcome.reason is None

