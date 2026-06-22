"""Change-ticket policy for write operations (shared by all chat adapters).

When enabled, a change (write/delete) won't be offered for approval unless the
request references a change ticket — e.g. a Jira key (INFRA-1234) or a
ServiceNow number (CHG0012345). The reference is recorded with the audit log.

This enforces that a *reference exists*; live verification against Jira/
ServiceNow (is it open? approved?) can be layered on by supplying a `verifier`.

Env:
  IACI_REQUIRE_CHANGE_TICKET=true|false   (default false)
  IACI_TICKET_PATTERN=<regex>             (override the default matcher)
"""
import os
import re

# Jira-style PROJ-123, and ServiceNow CHG/INC/RITM/CTASK numbers.
DEFAULT_PATTERN = r"\b(?:[A-Z][A-Z0-9]{1,9}-\d+|(?:CHG|INC|RITM|CTASK)\d{4,})\b"

# Common network/infra tokens that look like Jira keys but are NOT change tickets
# (e.g. "VLAN-100", "AS-65000"). Matches with these prefixes are ignored so they
# can't satisfy a change-ticket requirement.
_PREFIX_BLOCKLIST = {
    "VLAN", "VXLAN", "AS", "ASN", "DNS", "DHCP", "IPV4", "IPV6", "MAC", "ACL",
    "NAT", "BGP", "OSPF", "VRF", "SSID", "EUI", "MTU", "QOS", "TCP", "UDP",
}


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "t", "yes", "y")


class TicketPolicy:
    def __init__(self, required: bool = None, pattern: str = None, verifier=None):
        self.required = _env_bool("IACI_REQUIRE_CHANGE_TICKET", False) if required is None else required
        self.pattern = re.compile(pattern or os.getenv("IACI_TICKET_PATTERN", DEFAULT_PATTERN))
        # Optional callable(ref) -> (ok: bool, reason: str) for live verification.
        self.verifier = verifier

    def extract(self, text: str):
        """Returns the first plausible ticket reference in `text`, or None.
        Skips network-term look-alikes (VLAN-100, AS-65000, …)."""
        for m in self.pattern.finditer(text or ""):
            tok = m.group(0)
            prefix = re.split(r"[-\d]", tok, 1)[0].upper()  # letters before dash/digits
            if prefix in _PREFIX_BLOCKLIST:
                continue
            return tok
        return None

    def example(self) -> str:
        return "e.g. CHG0012345 or INFRA-1234"

    def check(self, text: str):
        """Returns (ok, ticket_or_none, reason). When not required, always ok."""
        if not self.required:
            return True, self.extract(text), ""
        ticket = self.extract(text)
        if not ticket:
            return False, None, (
                "This change requires a change-ticket reference in your request "
                f"({self.example()}). Re-send including the ticket.")
        if self.verifier:
            ok, reason = self.verifier(ticket)
            if not ok:
                return False, ticket, reason or f"Change ticket {ticket} is not valid/approved."
        return True, ticket, ""
