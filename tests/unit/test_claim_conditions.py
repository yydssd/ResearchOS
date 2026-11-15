"""Conditions describe the experimental setup a claim's number came from."""

from __future__ import annotations

from research_os.research.claims import extract_identity, may_merge
from research_os.research.conditions import extract_condition_map, extract_conditions
from research_os.research.scope import BlockScope


def test_backbone_is_extracted():
    assert extract_conditions("We train a Transformer-based model.") == ("backbone=transformer",)
    assert extract_conditions("A CNN backbone is used for comparison.") == ("backbone=cnn",)


def test_degradation_level_is_extracted():
    assert extract_conditions("At noise level 25 the gain is largest.") == ("degradation=25",)
    assert extract_conditions("Images suffer from heavy rain.") == ("degradation=heavy",)


def test_baseline_is_extracted():
    assert extract_conditions("Compared with MPRNet, the gain is 0.4 dB.") == ("baseline=mprnet",)


def test_training_protocol_is_extracted():
    assert extract_conditions("All models are trained from scratch.") == ("training=from-scratch",)


def test_multiple_kinds_are_sorted_and_deduplicated():
    text = "The Transformer model trained from scratch is compared with MPRNet."
    assert extract_conditions(text) == (
        "backbone=transformer",
        "baseline=mprnet",
        "training=from-scratch",
    )


def test_no_condition_means_empty_not_a_default():
    assert extract_conditions("Our method improves PSNR by 0.42 dB.") == ()


def test_conditions_carry_their_provenance():
    """Sentence-level conditions are stated by the sentence itself. That is the
    strongest tier, and the only one that can later support a contradiction:
    an inherited condition says "someone in this section said so", not "this
    claim used it"."""
    identity = extract_identity(
        "We train a Transformer backbone and improve PSNR on SIDD.",
        source_version_id="sv_1",
        scope=None,
        quantitative=[],
    )

    assert identity.conditions == ("backbone=transformer",)
    assert identity.condition_tiers == {"backbone": "sentence"}


def test_inherited_conditions_are_tagged_with_where_they_came_from():
    scope = BlockScope(
        task="denoising",
        datasets=frozenset({"SIDD"}),
        conditions={"backbone": "transformer"},
        condition_tiers={"backbone": "section-first-mention"},
    )

    identity = extract_identity(
        "The gain reaches 0.42 dB on SIDD.",
        source_version_id="sv_1",
        scope=scope,
        quantitative=[],
    )

    assert identity.conditions == ("backbone=transformer",)
    assert identity.condition_tiers == {"backbone": "section-first-mention"}


def test_no_conditions_means_no_provenance():
    identity = extract_identity(
        "Our method improves PSNR by 0.42 dB on SIDD.",
        source_version_id="sv_1",
        scope=None,
        quantitative=[],
    )

    assert identity.conditions == ()
    assert identity.condition_tiers == {}


def test_condition_map_is_the_primitive_and_the_tuple_is_derived():
    """`extract_conditions` keeps its tuple contract for every existing caller;
    the map is what per-kind provenance needs (S4)."""
    assert extract_condition_map("A Transformer trained from scratch.") == {
        "backbone": "transformer",
        "training": "from-scratch",
    }
    # Sorted by kind: `backbone` before `training`, deterministically.
    assert extract_conditions("A Transformer trained from scratch.") == (
        "backbone=transformer",
        "training=from-scratch",
    )
    # 设计 §8.1 / §9 / 交接 §9.4：值里的 ';' 会被 ";".join 撕成幽灵条件，
    # '|' 会把 identity_key 撕成第 8 段。两类必须拦在抽取器出口。
    # 实跑后果：值 "protocol=5-shot;x=y" → _conditions(claim) 解析成
    #   ('protocol=5-shot', 'x=y', 'scale=7b')，凭空多一个 kind；
    #   值 "protocol=zero|shot" → key.split("|") 得 8 段（应为 7）。
    for text in (
        "A Transformer trained from scratch.",
        "We train a 7B model.",
        "Experiments run on 8×A100 GPUs.",
        "We evaluate zero-shot.",
        "Reported under the 5-shot setting.",
        "It improves PSNR by 0.42 dB.",
        "At noise level 25 the gain is largest.",
        "Compared with MPRNet, the gain is 0.4 dB.",
    ):
        assert all(
            ";" not in value and "|" not in value
            for value in extract_condition_map(text).values()
        ), text


def test_model_scale_is_a_condition():
    """P4's seven dimensions include model scale (plan §16); it had no home."""
    assert extract_condition_map("We train a 7B model.") == {"scale": "7b"}
    assert extract_condition_map("Experiments run on 8×A100 GPUs.") == {"scale": "8xa100"}


def test_evaluation_protocol_is_a_condition():
    assert extract_condition_map("We evaluate zero-shot.") == {"protocol": "zero-shot"}
    assert extract_condition_map("Reported under the 5-shot setting.") == {"protocol": "5-shot"}

    # 设计 §9 / 交接 §9 起手第 3 条「必带对照测试」：仅在这两维不同的两句
    # → may_merge() == False（「字段有值」不算通过）。原计划把这条漏了，
    # 并入本用例，不新增用例数（累计数仍 +4）。
    a = extract_identity(
        "Our method improves PSNR on SIDD under zero-shot evaluation.",
        source_version_id="sv", scope=None, quantitative=[],
    )
    b = extract_identity(
        "Our method improves PSNR on SIDD under 5-shot evaluation.",
        source_version_id="sv", scope=None, quantitative=[],
    )
    c = extract_identity(
        "We train a 7B model and improve PSNR on SIDD.",
        source_version_id="sv", scope=None, quantitative=[],
    )
    d = extract_identity(
        "We train a 70B model and improve PSNR on SIDD.",
        source_version_id="sv", scope=None, quantitative=[],
    )
    assert a.conditions == ("protocol=zero-shot",)
    assert b.conditions == ("protocol=5-shot",)
    assert c.conditions == ("scale=7b",)
    assert d.conditions == ("scale=70b",)
    assert not may_merge(a, b) and not may_merge(c, d)
    assert may_merge(a, a)  # 对照：同设置仍能合并，不是「一律不合并」的假通过


def test_a_metric_is_not_a_protocol_and_a_unit_is_not_a_scale():
    """Same boundary as S2's MethodSetup (design §6.3): "success rate" is a metric
    and a dB value is a unit; reading either as a condition would let two claims
    look like they share a setup."""
    assert extract_condition_map("It improves PSNR by 0.42 dB.") == {}
    assert extract_condition_map("It reaches a 70% success rate.") == {}


def test_a_sentence_stating_one_kind_keeps_the_inherited_others():
    """The core of design §8.2: "ours reaches 70% with 5-shot" states a protocol
    and nothing else, so the section's backbone and training must survive, each
    with its own tier."""
    scope = BlockScope(
        task="denoising",
        datasets=frozenset({"SIDD"}),
        inherited_from={"conditions": "section-first-mention"},
        conditions={"backbone": "transformer", "training": "from-scratch"},
        condition_tiers={"backbone": "section-first-mention", "training": "section-first-mention"},
    )
    identity = extract_identity(
        "Our method reaches 70% with 5-shot on SIDD.",
        source_version_id="sv_1", scope=scope, quantitative=[],
    )

    assert identity.conditions == ("backbone=transformer", "protocol=5-shot", "training=from-scratch")
    assert identity.condition_tiers == {
        "protocol": "sentence",
        "backbone": "section-first-mention",
        "training": "section-first-mention",
    }


def test_a_sentence_kind_overrides_the_inherited_value_for_that_kind_only():
    scope = BlockScope(
        conditions={"backbone": "cnn"},
        condition_tiers={"backbone": "section-first-mention"},
    )
    identity = extract_identity(
        "The Transformer backbone improves PSNR on SIDD.",
        source_version_id="sv_1", scope=scope, quantitative=[],
    )

    assert identity.conditions == ("backbone=transformer",)
    assert identity.condition_tiers == {"backbone": "sentence"}
