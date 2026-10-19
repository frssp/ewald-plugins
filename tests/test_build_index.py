import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_index  # noqa: E402

GOOD = '''id = "demo"
name = "Demo"
summary = "A demo"
kinds = ["modifier"]
source = "pip:git+https://github.com/someone/ewald-demo@v0.1.0"
version = "0.1.0"
requires_ewald = ">=0.1, <1"
'''


def _check(tmp_path, text, name="demo"):
    path = tmp_path / f"{name}.toml"
    path.write_text(text)
    return build_index.check_entry(path)[1]


def test_good_entry(tmp_path):
    assert _check(tmp_path, GOOD) == []


def test_index_in_repo_is_current():
    assert build_index.main(["--check"]) == 0


def test_branch_source_is_rejected(tmp_path):
    problems = _check(tmp_path, GOOD.replace("@v0.1.0", "@main"))
    assert any("pin a tag or commit" in p for p in problems)


def test_unpinned_and_unknown_sources_are_rejected(tmp_path):
    assert _check(tmp_path, GOOD.replace("pip:git+https://github.com/someone/ewald-demo@v0.1.0", "pip:ewald-demo"))
    assert _check(tmp_path, GOOD.replace("pip:git+https://github.com/someone/ewald-demo@v0.1.0",
                                         "https://example.org/demo.py"))
    assert _check(tmp_path, GOOD.replace("pip:git+https://github.com/someone/ewald-demo@v0.1.0",
                                         "pip:ewald-demo==0.1.0")) == []


def test_bad_fields(tmp_path):
    assert any("file name" in p for p in _check(tmp_path, GOOD, name="other"))
    assert any("kinds" in p for p in _check(tmp_path, GOOD.replace('["modifier"]', '["widget"]')))
    assert any("requires_ewald" in p for p in _check(tmp_path, GOOD.replace(">=0.1, <1", "latest")))
    assert any("unknown key" in p for p in _check(tmp_path, GOOD + 'stars = 5\n'))
    assert any("missing 'summary'" in p for p in _check(tmp_path, GOOD.replace('summary = "A demo"\n', "")))
