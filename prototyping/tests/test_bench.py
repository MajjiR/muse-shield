from privacy_engine import bench


def test_generator_is_deterministic_and_grounded():
    a, b = bench.generate(40, seed=3), bench.generate(40, seed=3)
    assert [s.text for s in a] == [s.text for s in b]
    for s in a:
        for span in s.sensitive + s.public:
            assert span in s.text


def test_tradeoff_shape():
    rows = bench.run(n=80)["strategies"]
    assert rows["raw"]["leak_rate"] == 1.0 and rows["raw"]["utility"] == 1.0
    # Semantic tokens leak no more than redaction but keep far more utility.
    assert rows["semantic"]["leak_rate"] <= rows["redact"]["leak_rate"]
    assert rows["semantic"]["utility"] > rows["redact"]["utility"] + 0.4
    assert rows["semantic"]["restorable"] == 1.0
    # Teaching the user's own codenames and clients closes part of the gap.
    assert rows["semantic+taught"]["leak_rate"] < rows["semantic"]["leak_rate"]
    # Masking public context costs utility.
    assert rows["strict"]["over_mask_rate"] > 0 and rows["strict"]["context"] < 1.0


def test_render_includes_all_strategies():
    out = bench.render(bench.run(n=16))
    for name in bench.STRATEGIES:
        assert f"| {name} |" in out
