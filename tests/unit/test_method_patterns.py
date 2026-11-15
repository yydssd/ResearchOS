"""Every naming construction and vocabulary the method extractors use.

These tests are the contract for `patterns.py`: if a construction stops matching
"We introduce LangProp", the L1 layer silently drops to zero and every acceptance
number moves with it.
"""

from __future__ import annotations

from research_os.research.patterns import (
    COMPONENT_TAILS,
    COMPONENT_WORDS,
    EVAL_PROTOCOL,
    HYPERPARAMETERS,
    NAME_CONSTRUCTIONS,
    REPOSITORY_URL,
    SCALE_GPU,
    SCALE_PARAMS,
    domain_patterns,
)


def _names(text: str) -> list[str]:
    return [
        match.group("name")
        for _, pattern in NAME_CONSTRUCTIONS
        for match in pattern.finditer(text)
    ]


def test_all_three_naming_constructions_fire():
    assert _names("We introduce LangProp, a framework for policy learning.") == ["LangProp"]
    assert _names("Our framework, Voyager, learns an ever-growing skill library.") == ["Voyager"]
    assert _names("Voyager, our proposed method, stores code as skills.") == ["Voyager"]
    # The apposition must close with a comma. Without that requirement
    # "Then, the framework is applied" reads as a name - the one false positive
    # of this construction on the 40-paper hold-out set.
    assert _names("Then, the framework is applied to a policy.") == []


def test_a_lowercase_object_after_a_verb_is_not_a_name():
    """`[A-Z]` is load-bearing: without it "we propose a method that achieves"
    hands back "achieves", which then flows into every quantitative row."""
    assert _names("we propose a method that achieves 39.18 dB on SIDD.") == []
    assert _names("In this paper we propose a lightweight conditioning module.") == []
    assert _names("Motivated experiments show that our method improves PSNR.") == []


def test_scale_and_protocol_patterns_do_not_read_a_unit_as_a_scale():
    assert SCALE_PARAMS.findall("a 7B model") == [("7", "B")]
    assert SCALE_PARAMS.findall("1.3B parameters") == [("1.3", "B")]
    assert SCALE_PARAMS.findall("improves PSNR by 0.42 dB") == []
    assert SCALE_GPU.findall("trained on 8×A100 GPUs") == [("8", "A100")]


def test_protocol_vocabulary_is_closed():
    assert EVAL_PROTOCOL.findall("evaluated zero-shot and 5-shot, pass@1") == [
        "zero-shot",
        "5-shot",
        "pass@1",
    ]
    # A metric unit is not an evaluation protocol (design §6.3).
    assert EVAL_PROTOCOL.findall("39.18 dB PSNR and 0.95 SSIM") == []


def test_repository_and_hyperparameter_patterns():
    assert REPOSITORY_URL.findall("Code is at https://github.com/foo/bar.") == [
        "https://github.com/foo/bar."
    ]
    text = "trained for 100 epochs with learning rate 3e-4 and batch size 32 using AdamW"
    found = {name: pattern.findall(text) for name, pattern in HYPERPARAMETERS}
    assert found["lr"] == ["3e-4"]
    assert found["batch"] == ["32"]
    assert found["epochs"] == ["100"]
    assert found["optimizer"] == ["AdamW"]


def test_the_domain_hook_exists_but_is_empty():
    """Structure only: the Minecraft vocabulary is a separate design (§12.1).
    A test that pins it empty fails the day someone adds a group without saying
    why, which is the point."""
    assert domain_patterns(None).component_words == frozenset()
    assert domain_patterns("agent_in_mc").component_words == frozenset()
    # The design's own list (design §6.2), pinned so a word cannot appear or
    # vanish without the change showing up as a test diff. `transformer` is in it:
    # the point of this vocabulary is portability across domains, not that every
    # word is architectural in the narrow sense.
    assert COMPONENT_WORDS == frozenset(
        {
            "encoder", "decoder", "attention", "transformer", "memory", "planner",
            "buffer", "graph", "gate", "adapter", "head", "tokenizer", "retrieval",
        }
    )
    assert "module" in COMPONENT_TAILS
