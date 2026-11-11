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
    delays: dict[str, float] = field(default_factory=dict)

    @classmethod
    def parse(cls, text: str) -> "Robots":
        groups: dict[str, list[_Rule]] = {}
        delays: dict[str, float] = {}
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
            elif key == "crawl-delay":
                in_rules = True
                try:
                    delay = float(value)
                except ValueError:
                    continue
                for a in agents:
                    delays[a] = delay
        return cls(groups, delays)

    def _group(self, user_agent: str) -> str:
        """The group name that applies to this agent: a named group, else "*"."""
        token = user_agent.split("/", 1)[0].lower()
        return next((n for n in self.groups if n != "*" and n in token), "*")

    def crawl_delay(self, user_agent: str) -> float | None:
        """Not part of RFC 9309, but sites like AMD set it, and it costs nothing to honour."""
        return self.delays.get(self._group(user_agent))

    def allowed(self, user_agent: str, path_and_query: str) -> bool:
        rules = self.groups.get(self._group(user_agent), [])
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
