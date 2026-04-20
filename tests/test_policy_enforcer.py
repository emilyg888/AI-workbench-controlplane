from __future__ import annotations

from pathlib import Path

from workbench.policy.enforcer import PolicyEnforcer


def _write_pack(root: Path, body: str) -> Path:
    p = root / "data" / "policies" / "test.yaml"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body)
    return p


def test_regex_redact(workbench_root: Path) -> None:
    path = _write_pack(workbench_root, """
input_rules:
  - id: no_email
    type: regex_block
    pattern: '[\\w.+-]+@[\\w.-]+'
    action: redact
    message: "redacted"
""")
    e = PolicyEnforcer(str(path), root=workbench_root)
    r = e.check_input("contact me at test@example.com please")
    assert r.allowed is True
    assert "[REDACTED]" in r.transformed_text
    assert "no_email" in r.hit_rule_ids


def test_keyword_block_output(workbench_root: Path) -> None:
    path = _write_pack(workbench_root, """
output_rules:
  - id: no_advice
    type: keyword_block
    keywords: ['buy this stock']
    action: block
    replacement: "blocked"
""")
    e = PolicyEnforcer(str(path), root=workbench_root)
    r = e.check_output("You should buy this stock today")
    assert r.allowed is False
    assert r.action == "output_block"
    assert r.transformed_text == "blocked"


def test_missing_pack_allows_everything(workbench_root: Path) -> None:
    e = PolicyEnforcer("data/policies/does_not_exist.yaml", root=workbench_root)
    r = e.check_input("anything goes")
    assert r.allowed is True
    assert r.action == "allow"
