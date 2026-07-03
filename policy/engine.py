import redis
import json
import re
import os
import uuid
from datetime import datetime, timezone
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

            rule_type = rule.get("type")
            rule_tool = rule.get("tool", "*")

            if rule_type == "block":
                if rule_tool == tool_name or rule_tool == "*":
                    return PolicyDecision(
                        status="BLOCK",
                        reason=rule.get("reason", f"Tool '{tool_name}' is blocked by policy")
                    )

            if rule_type == "require_approval":
                if rule_tool == tool_name or rule_tool == "*":
                    return PolicyDecision(
                        status="PENDING_APPROVAL",
                        reason=f"Tool '{tool_name}' requires human approval"
                    )

            if rule_type == "input_validation":
                if rule_tool == tool_name or rule_tool == "*":
                    decision = self._validate_input(tool_name, tool_args, rule)
                    if decision:
                        return decision

            if rule_type == "budget":
                tokens_used = self._coerce_int(context.get("tokens_used", 0), default=0)
                max_tokens = self._coerce_int(rule.get("max_tokens"), default=10000)
                if tokens_used > max_tokens:
                    return PolicyDecision(
                        status="BLOCK",
                        reason=f"Token budget exceeded: {tokens_used} > {max_tokens}"
                    )

        return PolicyDecision(status="ALLOW")

    def _validate_input(self, tool_name: str, tool_args: dict, rule: dict) -> PolicyDecision | None:
        field = rule.get("field")
        if not field or field not in tool_args:
            return None

        value = str(tool_args[field])

        pattern = rule.get("pattern")
        if pattern:
            try:
                matches_pattern = re.match(pattern, value)
            except re.error as exc:
                return PolicyDecision(
                    status="BLOCK",
                    reason=f"Input validation policy is invalid for '{field}': {exc}"
                )
            if not matches_pattern:
                return PolicyDecision(
                    status="BLOCK",
                    reason=f"Input validation failed: '{field}' value '{value}' doesn't match pattern '{pattern}'"
                )

        max_length = rule.get("max_length")
        if max_length is not None:
            max_length = self._coerce_int(max_length, default=0)
            if len(value) > max_length:
                return PolicyDecision(
                    status="BLOCK",
                    reason=f"Input validation failed: '{field}' exceeds max length of {max_length}"
                )

        blocked_keywords = rule.get("blocked_keywords") or []
        if blocked_keywords:
            for keyword in blocked_keywords:
                if keyword.lower() in value.lower():
                    return PolicyDecision(
                        status="BLOCK",
                        reason=f"Input validation failed: '{field}' contains blocked keyword '{keyword}'"
                    )

        return None

    def _coerce_int(self, value, default: int) -> int:
        try:
            if value is None:
                return default
            return int(value)
        except (TypeError, ValueError):
            return default

    # ---- APPROVAL MANAGEMENT ----

    def create_pending_approval(
        self,
        conversation_id: str,
        tool_call: dict,
        reason: str,
        user_message: str = "",
    ) -> dict:
        approval_id = str(uuid.uuid4())
        record = {
            "id": approval_id,
            "status": "pending",
            "conversation_id": conversation_id,
            "tool_call": tool_call,
            "reason": reason,
            "user_message": user_message,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.redis.set(f"policy:approvals:{approval_id}", json.dumps(record))
        self.redis.lpush("policy:approvals:index", approval_id)
        self.redis.ltrim("policy:approvals:index", 0, 499)
        return record

    def get_approval(self, approval_id: str) -> dict | None:
        raw = self.redis.get(f"policy:approvals:{approval_id}")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def list_approvals(self, status: str | None = None) -> list:
        approvals = []
        seen = set()
        for approval_id in self.redis.lrange("policy:approvals:index", 0, -1):
            if approval_id in seen:
                continue
            seen.add(approval_id)
            approval = self.get_approval(approval_id)
            if not approval:
                continue
            if status and approval.get("status") != status:
                continue
            approvals.append(approval)
        return approvals

    def update_approval(self, approval_id: str, updates: dict) -> dict | None:
        approval = self.get_approval(approval_id)
        if not approval:
            return None
        approval.update(updates)
        approval["updated_at"] = datetime.now(timezone.utc).isoformat()
        self.redis.set(f"policy:approvals:{approval_id}", json.dumps(approval))
        return approval

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
