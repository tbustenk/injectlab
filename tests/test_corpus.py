"""Corpus loading, dev/test split, and end-to-end: every seed under every
mutation still fools the baseline mock (so no cell is a silent non-attack)."""

from injectlab import (
    Agent,
    MockModel,
    build_benign,
    build_scenario,
    load_corpus,
    mutations,
    new_canary,
    score_security,
    seeds_for_split,
)


def _run(scenario):
    canary = new_canary(seed="corpus")
    env = scenario.make_env(canary)
    result = Agent(MockModel()).run(scenario.user_request, env)
    return result, canary


def test_corpus_loads_with_valid_labels():
    carrier, seeds = load_corpus()
    assert seeds, "corpus should not be empty"
    assert len({s.id for s in seeds}) == len(seeds), "seed ids must be unique"
    for s in seeds:
        assert s.technique and s.goal
        assert s.split in ("dev", "test")


def test_dev_and_test_splits_are_disjoint_and_cover_all():
    _, seeds = load_corpus()
    dev = seeds_for_split(seeds, "dev")
    test = seeds_for_split(seeds, "test")
    assert dev and test
    assert {s.id for s in dev}.isdisjoint({s.id for s in test})
    assert len(dev) + len(test) == len(seeds)


def test_benign_control_reads_zero():
    carrier, _ = load_corpus()
    result, canary = _run(build_benign(carrier))
    v = score_security(result, canary)
    assert not v.attempted and not v.executed


def test_every_seed_x_default_mutation_is_a_real_attack_at_baseline():
    # Every destination-PRESERVING spelling must still succeed at baseline, so a
    # defense that moves the number gets the credit, not a broken attack.
    carrier, seeds = load_corpus()
    for seed in seeds:
        for mut in mutations.DEFAULT_MUTATIONS:
            scenario = build_scenario(carrier, seed, mutation=mut)
            result, canary = _run(scenario)
            v = score_security(result, canary)
            assert v.attempted and v.executed, (
                f"{seed.id} under {mut} did not succeed at baseline"
            )


def test_obfuscate_target_defeats_the_simple_mock():
    # The mock reads a contiguous address and cannot reconstruct a spaced one,
    # so it does NOT attack under obfuscate_target. That is the point: whether an
    # obfuscated destination still leaks is a question only a real model answers,
    # which is why this probe is run against a real model, never scored on the
    # mock. (The filter is bypassed regardless -- see test_defenses.)
    carrier, seeds = load_corpus()
    for seed in seeds:
        scenario = build_scenario(carrier, seed, mutation="obfuscate_target")
        result, canary = _run(scenario)
        v = score_security(result, canary)
        assert not v.executed, f"{seed.id}: mock unexpectedly read a spaced address"


def test_position_variants_build():
    carrier, seeds = load_corpus()
    seed = seeds[0]
    for pos in ("start", "middle", "end"):
        sc = build_scenario(carrier, seed, position=pos)
        assert seed.injection.split()[0].lower() in sc.document_text.lower() \
            or pos == "middle"  # middle may reflow; just ensure it builds
        assert sc.is_attack
