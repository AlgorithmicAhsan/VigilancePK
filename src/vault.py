import json
import os
import uuid
from typing import List, Dict
import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

# Cross-lingual model: lets an English query retrieve Urdu articles.
DEFAULT_EMBEDDING_MODEL = 'paraphrase-multilingual-MiniLM-L12-v2'

COLLECTION_NAME = "vigilance_pk_news"
# Cosine similarity for semantic search. This MUST be applied every time the
# collection is created, including after a wipe - Chroma silently falls back
# to L2 otherwise, which quietly changes retrieval ranking.
COLLECTION_METADATA = {"hnsw:space": "cosine"}


class Vault:
    def __init__(self, db_path=None, model_name=DEFAULT_EMBEDDING_MODEL):
        # Standardize paths relative to the script
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if db_path is None:
            db_path = os.path.join(base_dir, "data", "chroma_db")

        # Initialize Persistent Chroma Client
        self.client = chromadb.PersistentClient(path=db_path)

        # Initialize Embedding Model
        print(f"Loading multilingual embedding model: {model_name}...")
        self.model = SentenceTransformer(model_name, device='cpu')

        # Create or Get Collection
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata=COLLECTION_METADATA
        )

    def reset_collection(self):
        """Drops and recreates the collection, preserving the distance metric."""
        try:
            self.client.delete_collection(COLLECTION_NAME)
        except Exception as e:
            # Nothing to delete on a first run.
            print(f"Vault reset: no existing collection to drop ({e}).")
        self.collection = self.client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata=COLLECTION_METADATA
        )
        return self.collection

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
                "specific_tags": ",".join(classif.get('specific_tags', [])),
                "reasoning": classif.get('reasoning', '')
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
        
        # Report what was actually written, not what was read (they differ
        # whenever the batch contained duplicate links).
        print(f"Success! {len(documents)} articles added to the Vault.")

    def ingest_news(self, articles: list):
        """Ingests a list of article dicts directly (used by the /sync pipeline)."""
        if not articles:
            print("No articles to ingest.")
            return

        print(f"Ingesting {len(articles)} articles into the Vault...")
        documents, metadatas, ids = [], [], []
        ids_seen = set()

        for art in tqdm(articles):
            link = art.get('link', '')
            doc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, link))
            if doc_id in ids_seen:
                continue
            ids_seen.add(doc_id)

            doc_text = f"{art.get('title', '')}\n\n{art.get('summary', '')}"
            documents.append(doc_text)

            classif = art.get('jurist_classification', {})
            meta = {
                "source": art.get('source', 'Unknown'),
                "published": art.get('published', ''),
                "link": link,
                "image": art.get('image', ''),
                "language": art.get('language', 'english'),
                "category": art.get('category', classif.get('major_categories', ['General'])[0] if classif.get('major_categories') else 'General'),
                "severity": art.get('severity', 'medium'),
                "major_categories": ",".join(classif.get('major_categories', [])),
                "specific_tags": ",".join(classif.get('specific_tags', [])),
                # Why the Jurist tagged it this way (ADR-004). Without this the
                # reasoning was generated on every article and then discarded.
                "reasoning": classif.get('reasoning', '')
            }
            metadatas.append(meta)
            ids.append(doc_id)

        batch_size = 100
        for i in range(0, len(documents), batch_size):
            batch_docs = documents[i:i+batch_size]
            batch_metas = metadatas[i:i+batch_size]
            batch_ids = ids[i:i+batch_size]
            batch_embeddings = self.model.encode(batch_docs).tolist()
            self.collection.upsert(
                ids=batch_ids, embeddings=batch_embeddings,
                metadatas=batch_metas, documents=batch_docs
            )

        print(f"Success! {len(documents)} articles ingested via pipeline.")

    def search_news(self, query: str, top_k: int = 5):
        """Performs semantic search and returns a normalized list of hits.

        ChromaDB's native query() returns a dict-of-lists keyed by result type
        (documents/metadatas/distances), each wrapped in an outer list (one per
        query). Callers should not have to know that shape, so we flatten it
        into a simple list[dict] here:
            [{"document": str, "metadata": dict, "distance": float}, ...]
        """
        query_embedding = self.model.encode(query).tolist()

        raw = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )

        # Unwrap the single-query outer list, defaulting to empty on miss.
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]

        hits = []
        for i, doc in enumerate(documents):
            hits.append({
                "document": doc,
                "metadata": metadatas[i] if i < len(metadatas) else {},
                "distance": distances[i] if i < len(distances) else None,
            })
        return hits

if __name__ == "__main__":
    # --- Execute Ingestion ---
    vault = Vault()
    vault.ingest_json()
    
    # --- Quick Test Search ---
    print("\n--- Testing Search (RAG Engine Trial) ---")
    test_query = "human rights violations in election cases"
    results = vault.search_news(test_query, top_k=3)

    for i, hit in enumerate(results):
        dist = hit["distance"]
        dist_str = f"{dist:.4f}" if dist is not None else "n/a"
        print(f"\n[{i+1}] RELEVANCE: {dist_str}")
        print(f"TITLE: {hit['document'].splitlines()[0]}")  # First line is title
        print(f"TAGS: {hit['metadata'].get('specific_tags')}")
