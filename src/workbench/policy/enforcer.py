from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel


class PolicyResult(BaseModel):
    allowed: bool
    action: str  # "allow" | "input_redact" | "input_block" | "output_block"
    transformed_text: str
    hit_rule_ids: list[str] = []


def _load_pack(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


class PolicyEnforcer:
    def __init__(self, pack_ref: str, root: Path | None = None) -> None:
        self.pack_ref = pack_ref
        self.root = root or Path.cwd()
        p = Path(pack_ref)
        if not p.is_absolute():
            p = self.root / p
        pack = _load_pack(p)
        self.input_rules = list(pack.get("input_rules") or [])
        self.output_rules = list(pack.get("output_rules") or [])

    def check_input(self, text: str) -> PolicyResult:
        return self._apply(text, self.input_rules, default_action="allow",
                           pre_output=True)

    def check_output(self, text: str) -> PolicyResult:
        return self._apply(text, self.output_rules, default_action="allow",
                           pre_output=False)

    @staticmethod
    def _apply(text: str, rules: list[dict], default_action: str,
               pre_output: bool) -> PolicyResult:
        transformed = text
        hit_ids: list[str] = []
        final_action = default_action
        allowed = True
        for rule in rules:
            rid = rule.get("id", "unnamed")
            rtype = rule.get("type")
            action = rule.get("action", "block")
            matched = False
            if rtype == "regex_block":
                pattern = rule.get("pattern", "")
                if pattern and re.search(pattern, transformed):
                    matched = True
                    if action == "redact":
                        transformed = re.sub(pattern, "[REDACTED]", transformed)
                        final_action = "input_redact" if pre_output else "output_redact"
                    else:  # block
                        allowed = False
                        transformed = rule.get("message", "Blocked by policy.")
                        final_action = "input_block" if pre_output else "output_block"
            elif rtype == "keyword_block":
                for kw in rule.get("keywords", []) or []:
                    if kw and kw.lower() in transformed.lower():
                        matched = True
                        allowed = False
                        transformed = rule.get("replacement", "Blocked by policy.")
                        final_action = "input_block" if pre_output else "output_block"
                        break
            if matched:
                hit_ids.append(rid)
                if not allowed:
                    break
        return PolicyResult(
            allowed=allowed,
            action=final_action,
            transformed_text=transformed,
            hit_rule_ids=hit_ids,
        )
