"""Gemini (free tier) implementation of LlmProvider."""

from importlib import resources

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from app.llm.provider import Analysis, Busy, RateLimited

PROMPT = resources.files("app.llm").joinpath("prompts/analyze.txt").read_text()


class _TitleClass(BaseModel):
    is_internship: bool
    is_tech: bool


class GeminiProvider:
    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self.model = model

    async def _generate(self, contents: str, schema, system: str | None = None):
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0,
            system_instruction=system,
        )
        try:
            resp = await self._client.aio.models.generate_content(
                model=self.model, contents=contents, config=config
            )
        except errors.APIError as e:
            if e.code == 429:
                raise RateLimited(str(e)) from e
            if e.code in (500, 502, 503, 504):
                raise Busy(str(e)) from e
            raise
        return resp.parsed

    async def analyze(self, title: str, text: str) -> Analysis:
        parsed = await self._generate(
            f"Title: {title}\n\nPosting:\n{text[:30000]}", Analysis, PROMPT
        )
        return parsed if isinstance(parsed, Analysis) else Analysis.model_validate(parsed)

    async def classify_titles(self, titles: list[str]) -> list[tuple[bool, bool]]:
        listing = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(titles))
        prompt = (
            "For each job title, say whether it is an internship/trainee/student role and "
            "whether it is a tech role (software, data, AI, security, cloud, embedded, QA, IT, "
            f"research). Answer in the same order.\n\n{listing}"
        )
        parsed = await self._generate(prompt, list[_TitleClass])
        items = [
            p if isinstance(p, _TitleClass) else _TitleClass.model_validate(p) for p in parsed or []
        ]
        if len(items) != len(titles):
            raise ValueError("classification count mismatch")
        return [(i.is_internship, i.is_tech) for i in items]
