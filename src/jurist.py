import json
import os
import re
import concurrent.futures
from tqdm import tqdm
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
if os.getenv("GOOGLE_API_KEY"):
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

# Same setting the API uses, so the classifier model is named in one place.
DEFAULT_CLASSIFY_MODEL = os.getenv("CLASSIFY_MODEL", "models/gemini-2.5-flash")


class Jurist:
    def __init__(self, model=None):
        self.model = model or DEFAULT_CLASSIFY_MODEL
        # Full HRCP Taxonomy (Simplified for prompt efficiency)
        self.taxonomy = {
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
            "HRCP Activities": ["HRCP Activities"]
        }

    def categorize_article(self, article):
        """Classifies an article in a single high-precision pass with reasoning."""
        text = f"Title: {article.get('title', '')}\nSummary: {article.get('summary', '')}"
        
        system_instruction = (
            "You are an expert Human Rights Analyst specializing in the Pakistani context. "
            "Your task is to categorize news articles according to the HRCP (Human Rights Commission of Pakistan) taxonomy. "
            "STRICT RULES:\n"
            "1. Output valid JSON only.\n"
            "2. If an article is purely international or purely economic with no human rights angle, use 'General News' as the category.\n"
            "3. Be specific. If you pick a major category, you MUST pick relevant sub-tags."
        )

        prompt = f"""
        Analyze this article and identify:
        1. 1-3 Major Categories from the taxonomy below.
        2. 1-5 Specific Sub-Tags from the associated lists.
        3. A one-sentence reasoning for the classification.

        ARTICLE:
        {text}

        TAXONOMY:
        {json.dumps(self.taxonomy, indent=2)}

        OUTPUT FORMAT (JSON ONLY):
        {{
            "major_categories": ["Category 1"],
            "specific_tags": ["Tag A"],
            "reasoning": "Brief justification grounded in the article text."
        }}
        """

        try:
            model = genai.GenerativeModel(
                model_name=self.model,
                system_instruction=system_instruction
            )
            response = model.generate_content(
                prompt,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.1
                }
            )
            raw_response = response.text

            if not raw_response.strip():
                print(f"DEBUG: Empty response from model {self.model}")
                raise ValueError("Model returned an empty response.")

            # Clean Markdown wrappers if the AI included them.
            # Take what sits between the first fence pair; the old second
            # split() was a no-op because the delimiter was already consumed.
            fence = re.search(r"```(?:json)?\s*(.*?)```", raw_response, flags=re.DOTALL)
            if fence:
                raw_response = fence.group(1).strip()
            
            try:
                result = json.loads(raw_response)
            except json.JSONDecodeError:
                print(f"DEBUG: Failed to parse JSON. Raw start: {raw_response[:100]}...")
                raise

            major_cats = result.get('major_categories', [])
            specific_tags = result.get('specific_tags', [])

            # Ensure we have at least one category if empty
            if not major_cats:
                major_cats = ["General News"]
            
            article['jurist_classification'] = {
                "major_categories": major_cats,
                "specific_tags": specific_tags,
                "reasoning": result.get('reasoning', '')
            }
            return article

        except Exception as e:
            print(f"Classification Error: {e}")
            article['jurist_classification'] = {"major_categories": ["Uncategorized"], "specific_tags": [], "error": str(e)}
            return article


    def process_all(self, input_file=None, output_file=None, max_workers=2):
        """Processes articles in parallel for maximum speed."""
        # Standardize paths relative to the script
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

        print(f"Analyzing {len(articles)} articles with {max_workers} parallel threads using {self.model}...")
        
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Use tqdm for progress tracking
            futures = [executor.submit(self.categorize_article, art) for art in articles]
            for future in tqdm(concurrent.futures.as_completed(futures), total=len(articles)):
                results.append(future.result())

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=4)
        
        print(f"Success! Categorized data saved to {output_file}")

if __name__ == "__main__":
    # Milestone Execution: Phase 3
    # Model comes from CLASSIFY_MODEL in .env.
    jurist = Jurist()
    print(f"Classifying with: {jurist.model}")
    jurist.process_all(max_workers=2) # Lower concurrency for free tier stability
