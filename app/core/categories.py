"""Kinds of tech internship, for sorting jobs and writing one resume per kind.

Gemini picks one when it reads a job; jobs it hasn't read yet get one from their title
(40 titles per request). The slug is stored on jobs.category; the label is what people see.
"""

from typing import Literal

Category = Literal[
    "swe", "ml", "data", "hardware", "cloud", "security", "quant", "qa", "research", "it",
    "other",
]  # fmt: skip

# slug -> (label, what belongs there; the second part goes into Gemini's instructions)
CATEGORIES: dict[str, tuple[str, str]] = {
    "swe": (
        "Software Engineering",
        "general software development: backend, frontend, full-stack, mobile, platform, tools",
    ),
    "ml": ("ML / AI", "machine learning, deep learning, AI, LLMs, computer vision, NLP"),
    "data": ("Data", "data science, data analytics, data engineering, business intelligence"),
    "hardware": (
        "Hardware / Embedded",
        "embedded, firmware, VLSI, chip design and verification, electronics, robotics hardware",
    ),
    "cloud": ("Cloud / DevOps", "cloud, DevOps, SRE, infrastructure, networking"),
    "security": ("Security", "cybersecurity, application or network security"),
    "quant": ("Quant", "quantitative research, trading, quant development at trading firms"),
    "qa": ("QA / Test", "software testing, quality assurance, test automation"),
    "research": (
        "Research",
        "technical research not covered above, e.g. research scientist roles in systems or theory",
    ),
    "it": ("IT / Support", "IT support, technical support, IT operations, systems administration"),
    "other": ("Other tech", "technical roles that fit none of the above, e.g. technical product"),
}

LABEL = {slug: label for slug, (label, _) in CATEGORIES.items()}


def category_guide() -> str:
    return "\n".join(f"   - {slug}: {what}" for slug, (_, what) in CATEGORIES.items())
