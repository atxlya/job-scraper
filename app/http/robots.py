"""robots.txt matching per RFC 9309: the longest matching rule wins, ties go to Allow.

Python's urllib.robotparser applies rules in file order instead, which wrongly blocks
files like NVIDIA's ("Disallow: /" followed by "Allow: /api/pcsx").
"""

import re
from dataclasses import dataclass, field


@dataclass
class _Rule:
    allow: bool
    pattern: str
    regex: re.Pattern = field(repr=False)


def _compile(pattern: str) -> re.Pattern:
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    rx = "".join(".*" if ch == "*" else re.escape(ch) for ch in body)
    return re.compile(rx + ("$" if anchored else ""))


@dataclass
class Robots:
    groups: dict[str, list[_Rule]]

    @classmethod
    def parse(cls, text: str) -> "Robots":
        groups: dict[str, list[_Rule]] = {}
        agents: list[str] = []
        in_rules = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (p.strip() for p in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if in_rules:
                    agents, in_rules = [], False
                agents.append(value.lower())
                for a in agents:
                    groups.setdefault(a, [])
            elif key in ("allow", "disallow"):
                in_rules = True
                if not value:
                    continue  # "Disallow:" with no path means allow all
                for a in agents:
                    groups[a].append(_Rule(key == "allow", value, _compile(value)))
        return cls(groups)

    def allowed(self, user_agent: str, path_and_query: str) -> bool:
        token = user_agent.split("/", 1)[0].lower()
        rules = next(
            (r for name, r in self.groups.items() if name != "*" and name in token),
            self.groups.get("*", []),
        )
        best: _Rule | None = None
        for rule in rules:
            if rule.regex.match(path_and_query):
                if (
                    best is None
                    or len(rule.pattern) > len(best.pattern)
                    or (len(rule.pattern) == len(best.pattern) and rule.allow)
                ):
                    best = rule
        return True if best is None else best.allow
