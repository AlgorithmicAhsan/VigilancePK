import json
import os
import uuid
from typing import List, Dict
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

class Vault:
    def __init__(self, db_path=None, model_name='all-MiniLM-L6-v2'):
        # Standardize paths relative to the script
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if db_path is None:
            db_path = os.path.join(base_dir, "data", "chroma_db")
        
        # Initialize Persistent Chroma Client
        self.client = chromadb.PersistentClient(path=db_path)
        
        # Initialize Embedding Model
        print(f"Loading embedding model: {model_name}...")
        self.model = SentenceTransformer(model_name)
        
        # Create or Get Collection
        self.collection = self.client.get_or_create_collection(
            name="vigilance_pk_news",
            metadata={"hnsw:space": "cosine"} # Using cosine similarity for semantic search
        )

    def ingest_json(self, json_file=None):
        """Loads categorized news from JSON and stores in ChromaDB."""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if json_file is None:
            json_file = os.path.join(base_dir, "data", "categorized_news.json")
            
        if not os.path.exists(json_file):
            print(f"Error: {json_file} not found.")
            return

        with open(json_file, "r", encoding="utf-8") as f:
            articles = json.load(f)

        print(f"Ingesting {len(articles)} articles into the Vault...")
        
        documents = []
        metadatas = []
        ids = []
        
        ids_seen = set()
        for art in tqdm(articles):
            link = art.get('link', '')
            # Generate unique ID from link
            doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, link))
            
            # Simple in-memory deduplication for the current batch
            if doc_id in ids_seen:
                continue
            ids_seen.add(doc_id)

            # 1. Create a searchable text string (Document)
            doc_text = f"{art.get('title', '')}\n\n{art.get('summary', '')}"
            documents.append(doc_text)
            
            # 2. Extract Metadata
            classif = art.get('jurist_classification', {})
            meta = {
                "source": art.get('source', 'Unknown'),
                "published": art.get('published', ''),
                "link": link,
                "language": art.get('language', 'english'),
                "major_categories": ",".join(classif.get('major_categories', [])),
                "specific_tags": ",".join(classif.get('specific_tags', []))
            }
            metadatas.append(meta)
            ids.append(doc_id)

        # Bulk Upsert to ChromaDB
        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i+batch_size]
            batch_metas = metadatas[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            
            # Use our local model to generate embeddings
            # This prevents ChromaDB from trying to download the model again
            batch_embeddings = self.model.encode(batch_docs).tolist()

            self.collection.upsert(
                ids=batch_ids,
                embeddings=batch_embeddings,
                metadatas=batch_metas,
                documents=batch_docs
            )
        
        print(f"Success! {len(articles)} articles added to the Vault.")

    def search_news(self, query: str, top_k: int = 5):
        """Performs semantic search across the news repository."""
        # Generate embedding for the query
        query_embedding = self.model.encode(query).tolist()
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        return results

if __name__ == "__main__":
    # --- Execute Ingestion ---
    vault = Vault()
    vault.ingest_json()
    
    # --- Quick Test Search ---
    print("\n--- Testing Search (RAG Engine Trial) ---")
    test_query = "human rights violations in election cases"
    results = vault.search_news(test_query, top_k=3)
    
    for i, doc in enumerate(results['documents'][0]):
        print(f"\n[{i+1}] RELEVANCE: {results['distances'][0][i]:.4f}")
        print(f"TITLE: {doc.splitlines()[0]}") # First line is title
        print(f"TAGS: {results['metadatas'][0][i].get('specific_tags')}")
