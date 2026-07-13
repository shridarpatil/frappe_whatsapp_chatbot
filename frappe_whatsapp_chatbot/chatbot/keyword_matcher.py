import frappe
import re
from datetime import datetime


class KeywordMatcher:
    """Match incoming messages against keyword rules."""

    def __init__(self, whatsapp_account=None):
        self.account = whatsapp_account
        self.rules = self.load_rules()

    def load_rules(self):
        """Load active keyword rules sorted by priority."""
        try:
            rules = frappe.get_all(
                "WhatsApp Keyword Reply",
                filters={"enabled": 1},
                fields=["*"],
                order_by="priority desc"
            )

            # Filter by account and date range
            now = datetime.now()
            valid_rules = []

            for rule in rules:
                # Check account filter
                if rule.whatsapp_account and rule.whatsapp_account != self.account:
                    continue

                # Check date range
                if rule.active_from and now < rule.active_from:
                    continue
                if rule.active_until and now > rule.active_until:
                    continue

                valid_rules.append(rule)

            return valid_rules

        except Exception as e:
            frappe.log_error(f"KeywordMatcher load_rules error: {str(e)}")
            return []

    def match(self, message_text):
        """Find matching keyword rule for message."""
        if not message_text:
            return None

        for rule in self.rules:
            if self.rule_matches(rule, message_text):
                # Check additional conditions
                if rule.conditions:
                    if not self.evaluate_conditions(rule.conditions, message_text):
                        continue
                return frappe.get_doc("WhatsApp Keyword Reply", rule.name)

        return None

    def rule_matches(self, rule, message_text):
        """Check if a rule matches the message."""
        if not rule.keywords:
            return False

        keywords = [k.strip() for k in rule.keywords.split(",") if k.strip()]

        text = message_text if rule.case_sensitive else message_text.lower()

        for keyword in keywords:
            kw = keyword if rule.case_sensitive else keyword.lower()

            if rule.match_type == "Exact":
                if text == kw:
                    return True

            elif rule.match_type == "Contains":
                if kw in text or kw == "*":
                    return True

            elif rule.match_type == "Starts With":
                if text.startswith(kw):
                    return True

            elif rule.match_type == "Regex":
                try:
                    flags = 0 if rule.case_sensitive else re.IGNORECASE
                    if re.search(kw, message_text, flags):
                        return True
                except re.error as e:
                    frappe.log_error(
                        f"Invalid regex in keyword rule '{rule.name}': {str(e)}"
                    )

        return False

    def evaluate_conditions(self, conditions, message_text):
        """Evaluate Python conditions for rule."""
        try:
            # Create a safe evaluation context
            eval_globals = {
                "message": message_text,
                "len": len,
                "str": str,
                "int": int,
                "float": float,
                "bool": bool,
            }

            return frappe.safe_eval(
                conditions,
                eval_globals=eval_globals,
                eval_locals={}
            )
        except Exception as e:
            frappe.log_error(f"Condition evaluation error: {str(e)}")
            return False
