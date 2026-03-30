import json
import os
import concurrent.futures
from tqdm import tqdm
import ollama

class Jurist:
    def __init__(self, model="llama3.1:8b"):
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
        """Classifies a single article using a high-precision two-pass logic."""
        text = f"Title: {article.get('title', '')}\nSummary: {article.get('summary', '')}"
        
        # --- PASS 1: Select Broad Categories ---
        pass1_prompt = f"""
        Identify the 1-3 most relevant Major Categories for this Pakistani news article.
        
        ARTICLE:
        {text}
        
        AVAILABLE MAJOR CATEGORIES:
        {list(self.taxonomy.keys())}
        
        EXAMPLES:
        - "Court stays execution": ["Judicial System", "Crimes & Violations"]
        - "Rupee drops against dollar": ["Economy"]
        - "Digital census starts in Karachi": ["Governance"]

        OUTPUT FORMAT (JSON):
        {{"major_categories": ["..."]}}
        """

        try:
            # First LLM call
            res1 = ollama.generate(model=self.model, prompt=pass1_prompt, format='json')
            major_cats = json.loads(res1['response']).get('major_categories', [])
            
            # --- PASS 2: Surgical Tagging ---
            # Filter taxonomy to only show relevant sub-tags
            filtered_taxonomy = {cat: self.taxonomy[cat] for cat in major_cats if cat in self.taxonomy}
            if not filtered_taxonomy:
                filtered_taxonomy = {"Other": ["General News"]}

            pass2_prompt = f"""
            Identify 1-3 Specific Sub-Tags from the lists of the selected Categories.
            
            ARTICLE:
            {text}
            
            SELECTED CATEGORIES & THEIR TAGS:
            {json.dumps(filtered_taxonomy, indent=2)}
            
            INSTRUCTIONS:
            1. Only pick tags from the lists provided.
            2. CRITICAL: Do NOT pick the Category Name itself (e.g., if Category is 'Economy', do NOT pick 'Economy' as a tag—pick 'Inflation' or 'Poverty').
            3. Do NOT pick 'Suicide attacks' or 'Terrorism' unless the text explicitly mentions them.

            OUTPUT FORMAT (JSON):
            {{"specific_tags": ["..."]}}
            """

            # Second LLM call
            res2 = ollama.generate(model=self.model, prompt=pass2_prompt, format='json')
            specific_tags = json.loads(res2['response']).get('specific_tags', [])

            # Post-processing: Remove redundant Major Category names from the tags
            clean_tags = [t for t in specific_tags if t not in major_cats]
            
            # Fallback if list is empty after cleaning
            if not clean_tags and specific_tags:
                clean_tags = specific_tags

            article['jurist_classification'] = {
                "major_categories": major_cats,
                "specific_tags": clean_tags
            }
            return article

        except Exception as e:
            article['jurist_classification'] = {"error": f"Precision Fail: {str(e)}"}
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
    jurist = Jurist(model="llama3.1:8b")
    jurist.process_all(max_workers=4) # Concurrency level 2 for 12GB VRAM stability
