import json
import os
import concurrent.futures
from tqdm import tqdm
import google.generativeai as genai
import ollama
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
if os.getenv("GOOGLE_API_KEY"):
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

class Jurist:
    def __init__(self, model="qwen3:4b"):
        self.model = model
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

        ARTICLE:
        {text}

        TAXONOMY:
        {json.dumps(self.taxonomy, indent=2)}

        OUTPUT FORMAT:
        {{
            "reasoning": "brief explanation of why these categories apply",
            "major_categories": ["Category 1", "Category 2"],
            "specific_tags": ["Tag A", "Tag B"]
        }}
        """

        try:
            # Detect Model Type
            if "gemini" in self.model.lower():
                # --- GEMINI API PATH ---
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
                result = json.loads(response.text)
            else:
                # --- OLLAMA LOCAL PATH ---
                # Combine system instruction and prompt for Ollama
                ollama_prompt = f"{system_instruction}\n\n{prompt}"
                response = ollama.generate(
                    model=self.model,
                    prompt=ollama_prompt,
                    format='json',
                    options={"temperature": 0.1}
                )
                result = json.loads(response['response'])
            
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
            article['jurist_classification'] = {
                "major_categories": ["Uncategorized"],
                "specific_tags": [],
                "error": str(e)
            }
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
    # Ensure you have the model pulled: ollama pull llama3.1:8b
    jurist = Jurist(model="gemini-flash-latest")
    jurist.process_all(max_workers=2) # Lower concurrency for free tier stability
