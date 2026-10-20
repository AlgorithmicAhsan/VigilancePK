import json
import os
import re
from typing import Literal
from pydantic import BaseModel
from src import llm

# Articles per model call (ADR-018). One call per article used to blow the
# free-tier quota on the first sync; 20 per call cuts requests ~20x and sends
# the taxonomy once per batch instead of once per article.
BATCH_SIZE = int(os.getenv("CLASSIFY_BATCH_SIZE", "20"))

# Summaries are capped so one long article cannot crowd a batch prompt.
SUMMARY_CHARS = 600

GENERAL = "General News"

# Full HRCP Taxonomy (Simplified for prompt efficiency)
TAXONOMY = {
    "Civil Rights": ["Freedom of expression", "Freedom of Peaceful assembly", "Freedom of association", "Freedom of movement", "Digital Rights", "Due process and fair trial"],
    "Vulnerable Groups": ["Women", "Children", "Religious minorities and sects", "Transgender persons", "Industrial labour", "Agricultural labour", "Fisherfolk", "Miners", "Refugees", "IDPs", "Stateless persons", "Disabled", "Elderly"],
    "Education": ["Higher Education", "Primary & Secondary Education", "Private Schools", "Madrassas", "Curriculum"],
    "Governance": ["Federal Government", "Provincial Government", "Policies & Expenditure", "Infrastructure", "Census", "Local Government"],
    "Parliament": ["Senate", "National Assembly", "Laws and ordinances"],
    "Provincial Assemblies": ["Balochistan", "Punjab", "Sindh", "KP", "Gilgit Baltistan", "AJK"],
    "Armed Forces": ["COAS", "ISPR", "Navy", "Intelligence Agencies"],
    "Crimes & Violations": ["Extrajudicial killing", "Enforced disappearances", "Blasphemy", "Trafficking", "Death penalty", "Law and order"],
    "Accountability": ["18th Amendment", "Constitutional amendments", "Inter-provincial issues"],
    "Economy": ["Poverty", "Inflation", "Budget", "Unemployment"],
    "Health": ["COVID", "Dengue", "Polio", "Public Health", "Suicide", "Mental health"],
    "Housing & Utilities": ["Housing", "Encroachments", "Public utilities", "Water and sanitation"],
    "Law Enforcement": ["FIA", "Police", "CTD", "Rangers", "Jails", "Custodial torture"],
    "Political Parties": ["PML-N", "PML-Q", "PPP", "PTI", "ANP", "MQM", "Religious Parties"],
    "Gender-Based Violence": ["Physical violence", "Sexual violence", "Domestic violence", "Psychological violence", "Harmful practices"],
    "Terrorism & Extremism": ["Militancy", "Suicide attacks", "Extremist groups", "Terrorist groups", "Sectarian Groups", "Sectarian conflict"],
    "Democracy & Elections": ["ECP", "Election observers", "Electoral laws", "Constituency delimitations", "Civil society", "Indo-Pak relations"],
    "Environment": ["Degradation", "Climate Change", "Pollution", "Floods", "Natural disasters"],
    "Judicial System": ["Supreme Court", "High Courts", "District courts", "Anti-terrorism courts", "GBV courts", "Military Courts", "Jirgas", "Judicial Reforms"],
    "HRCP Activities": ["HRCP Activities"],
}
TAG_TO_CATEGORY = {tag: cat for cat, tags in TAXONOMY.items() for tag in tags}

# Severity measures the harm reported, not the topic (ADR-024). The old
# topic rules rated any Armed Forces story "high" and sexual violence "low".
SEVERITY_LEVELS = ("critical", "high", "medium", "low")

SEVERITY_RUBRIC = (
    "SEVERITY - rate the human rights harm the article reports, never its topic or tone.\n"
    "Harm counts when people, groups or the state cause it, or when the state fails to prevent it "
    "through negligence (e.g. deaths from unsafe public infrastructure). Accidents and natural deaths "
    "with no one responsible are low.\n"
    "- critical: loss of life or a threat to life (killings, custodial deaths, "
    "enforced disappearances, mob attacks, bombings).\n"
    "- high: serious harm or loss of liberty (torture, sexual violence, injuries, "
    "arbitrary arrest or detention, forced conversion or marriage, child abuse, forced displacement). "
    "A routine arrest of a criminal suspect is low unless the article reports abuse or a denial of due process.\n"
    "- medium: rights restricted without physical harm (censorship, protest bans, "
    "discriminatory laws, threats, harassment, denial of services).\n"
    "- low: context only (policy debate, statements, general news).\n"
    "TIMING: follow-up reporting on a recent case (investigation, arrest, trial, funeral, inquiry "
    "findings) takes the severity of the harm in that case. Retrospectives or anniversaries about "
    "events years ago are low, as is hypothetical or figurative harm.\n"
    "SCOPE: events outside Pakistan with no Pakistani victims are low.\n"
    "Raise the level by one if the victims are children or many people are affected.\n"
    "The reasoning sentence must name the harm that set the severity."
)

SYSTEM_INSTRUCTION = (
    "You are an expert Human Rights Analyst specializing in the Pakistani context. "
    "You categorize news articles (English or Urdu) according to the HRCP "
    "(Human Rights Commission of Pakistan) taxonomy and rate their severity.\n"
    "STRICT RULES:\n"
    "1. Use category and tag names EXACTLY as written in the taxonomy.\n"
    f"2. If an article has no human rights angle, use '{GENERAL}' as its only category and no tags.\n"
    "3. Be specific. If you pick a major category, pick relevant sub-tags from it.\n"
    "4. Return exactly one result per article, using the article's id.\n\n"
    + SEVERITY_RUBRIC
)


# Field order is the order the model writes in. Reasoning comes before
# severity so the rating follows from the stated harm, not the other way round.
class ArticleLabels(BaseModel):
    id: int
    major_categories: list[str]
    specific_tags: list[str]
    reasoning: str
    severity: Literal["critical", "high", "medium", "low"]


def build_prompt(articles) -> str:
    lines = []
    for i, art in enumerate(articles):
        summary = (art.get("summary") or "")[:SUMMARY_CHARS]
        lines.append(f"[id={i}]\nTitle: {art.get('title', '')}\nSummary: {summary}")
    return (
        "For EACH article below give:\n"
        "1. 1-3 major_categories from the taxonomy.\n"
        "2. 1-5 specific_tags from those categories' lists.\n"
        "3. reasoning: one sentence grounded in the article text, naming the harm reported now (if any).\n"
        "4. severity: critical, high, medium or low, following from that reasoning and the severity rules.\n\n"
        f"TAXONOMY:\n{json.dumps(TAXONOMY)}\n\n"
        "ARTICLES:\n" + "\n\n".join(lines)
    )


def parse_batch(raw: str, count: int) -> dict:
    """Turns the model's JSON into {article index: clean labels}.

    Anything not in the taxonomy is dropped rather than stored, so the
    feed only ever shows real HRCP categories. Indexes the model skipped or
    mangled are simply absent from the result: the caller treats them as
    failures and they are retried on the next sync.
    """
    # The JSON mime type should make fences impossible; this is a cheap guard.
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, flags=re.DOTALL)
    if fence:
        raw = fence.group(1)
    items = json.loads(raw)
    if not isinstance(items, list):
        raise ValueError("Expected a JSON list of results.")

    results = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        idx = item.get("id")
        if not isinstance(idx, int) or not 0 <= idx < count or idx in results:
            continue
        severity = str(item.get("severity") or "").lower()
        if severity not in SEVERITY_LEVELS:
            # No guessed severity: a wrong "low" could hide a killing. The
            # article counts as failed and is retried (same rule as ADR-015).
            continue

        tags = [t for t in item.get("specific_tags") or [] if t in TAG_TO_CATEGORY]
        cats = [c for c in item.get("major_categories") or [] if c in TAXONOMY]
        if not cats:
            # Model named valid tags but garbled the category: recover it.
            cats = list(dict.fromkeys(TAG_TO_CATEGORY[t] for t in tags)) or [GENERAL]

        results[idx] = {
            "major_categories": cats[:3],
            "specific_tags": tags[:5],
            "severity": severity,
            "reasoning": str(item.get("reasoning") or "")[:300],
        }
    return results


class Jurist:
    def __init__(self, model=None, batch_size=BATCH_SIZE):
        self.model = model or llm.CLASSIFY_MODEL
        self.batch_size = batch_size

    def classify_batch(self, articles):
        """Labels articles in place. Returns (classified, failed)."""
        try:
            raw = llm.generate_json(
                build_prompt(articles), SYSTEM_INSTRUCTION,
                model=self.model, schema=list[ArticleLabels],
            )
            labels = parse_batch(raw, len(articles))
        except Exception as e:
            print(f"Classification batch failed ({len(articles)} articles): {e}")
            for art in articles:
                art["classification_error"] = str(e)[:200]
            return [], list(articles)

        classified, failed = [], []
        for i, art in enumerate(articles):
            result = labels.get(i)
            if result is None:
                art["classification_error"] = "No result returned for this article."
                failed.append(art)
                continue
            art["jurist_classification"] = result
            art["category"] = result["major_categories"][0]
            art["tags"] = ",".join(result["specific_tags"])
            art["severity"] = result["severity"]
            classified.append(art)
        return classified, failed

    def classify_all(self, articles):
        """Sequential batches: one request at a time stays inside the
        per-minute quota, and the SDK backs off if we still hit it."""
        classified, failed = [], []
        for start in range(0, len(articles), self.batch_size):
            batch = articles[start:start + self.batch_size]
            ok, bad = self.classify_batch(batch)
            classified += ok
            failed += bad
            print(f"Classified {start + len(batch)}/{len(articles)} ({len(failed)} failed so far)")
        return classified, failed

    def process_all(self, input_file=None, output_file=None):
        """Classifies a JSON file of articles and writes the successes."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if input_file is None:
            input_file = os.path.join(base_dir, "data", "filtered_news.json")
        if output_file is None:
            output_file = os.path.join(base_dir, "data", "categorized_news.json")

        if not os.path.exists(input_file):
            print(f"Error: {input_file} not found.")
            return

        with open(input_file, "r", encoding="utf-8") as f:
            articles = json.load(f)

        print(f"Analyzing {len(articles)} articles in batches of {self.batch_size} using {self.model}...")
        classified, failed = self.classify_all(articles)

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(classified, f, ensure_ascii=False, indent=4)

        print(f"Saved {len(classified)} classified articles to {output_file} ({len(failed)} failed, not saved).")


if __name__ == "__main__":
    # Model comes from CLASSIFY_MODEL in .env.
    jurist = Jurist()
    print(f"Classifying with: {jurist.model}")
    jurist.process_all()
