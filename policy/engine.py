import redis
import json
import re
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class PolicyDecision:
    status: str 
    reason: str = ""

class PolicyEngine:
    def __init__(self):
        self.redis = redis.Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379"),
            decode_responses=True
        )

    def load_rules(self) -> list:
        try:
            raw = self.redis.get("policy:rules")
            if not raw:
                return []
            return json.loads(raw)
        except Exception:
            return []

    def evaluate(self, tool_name: str, tool_args: dict, context: dict) -> PolicyDecision:
        injection = self._check_prompt_injection(tool_args)
        if injection:
            return PolicyDecision(
                status="BLOCK",
                reason=f"Prompt injection detected: '{injection}'"
            )

        rules = self.load_rules()

        for rule in rules:
            if not rule.get("enabled", True):
                continue

            if rule["type"] == "block":
                if rule["tool"] == tool_name or rule["tool"] == "*":
                    return PolicyDecision(
                        status="BLOCK",
                        reason=rule.get("reason", f"Tool '{tool_name}' is blocked by policy")
                    )

            if rule["type"] == "require_approval":
                if rule["tool"] == tool_name:
                    return PolicyDecision(
                        status="PENDING_APPROVAL",
                        reason=f"Tool '{tool_name}' requires human approval"
                    )

            if rule["type"] == "input_validation":
                if rule["tool"] == tool_name:
                    decision = self._validate_input(tool_name, tool_args, rule)
                    if decision:
                        return decision

            if rule["type"] == "budget":
                tokens_used = context.get("tokens_used", 0)
                if tokens_used > rule.get("max_tokens", 10000):
                    return PolicyDecision(
                        status="BLOCK",
                        reason=f"Token budget exceeded: {tokens_used} > {rule['max_tokens']}"
                    )

        return PolicyDecision(status="ALLOW")

    def _validate_input(self, tool_name: str, tool_args: dict, rule: dict) -> PolicyDecision | None:
        field = rule.get("field")
        if not field or field not in tool_args:
            return None

        value = str(tool_args[field])

        if "pattern" in rule:
            if not re.match(rule["pattern"], value):
                return PolicyDecision(
                    status="BLOCK",
                    reason=f"Input validation failed: '{field}' value '{value}' doesn't match pattern '{rule['pattern']}'"
                )

        if "max_length" in rule:
            if len(value) > rule["max_length"]:
                return PolicyDecision(
                    status="BLOCK",
                    reason=f"Input validation failed: '{field}' exceeds max length of {rule['max_length']}"
                )

        if "blocked_keywords" in rule:
            for keyword in rule["blocked_keywords"]:
                if keyword.lower() in value.lower():
                    return PolicyDecision(
                        status="BLOCK",
                        reason=f"Input validation failed: '{field}' contains blocked keyword '{keyword}'"
                    )

        return None

    def _check_prompt_injection(self, tool_args: dict) -> str | None:
        INJECTION_PATTERNS = [
            "ignore previous instructions",
            "ignore all instructions",
            "you are now",
            "bypass",
            "forget your rules",
            "system prompt",
            "jailbreak",
            "disregard",
            "override policy",
            "act as if",
        ]

        all_values = " ".join(str(v) for v in tool_args.values()).lower()

        for pattern in INJECTION_PATTERNS:
            if pattern in all_values:
                return pattern

        return None

    # ---- RULE MANAGEMENT ----
    # These are called by the dashboard API

    def save_rules(self, rules: list):
        self.redis.set("policy:rules", json.dumps(rules))

    def get_rules(self) -> list:
        return self.load_rules()

    def add_rule(self, rule: dict):
        rules = self.load_rules()
        rules.append(rule)
        self.save_rules(rules)

    def delete_rule(self, rule_id: str):
        rules = self.load_rules()
        rules = [r for r in rules if r.get("id") != rule_id]
        self.save_rules(rules)

    def toggle_rule(self, rule_id: str, enabled: bool):
        rules = self.load_rules()
        for rule in rules:
            if rule.get("id") == rule_id:
                rule["enabled"] = enabled
        self.save_rules(rules)