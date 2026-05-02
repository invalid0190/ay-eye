import json
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rag.rag_manager import rag_manager
from core.utils.logger import logger

def ingest_seed():
    seed_path = os.path.join("data", "rag", "seed_rules.json")
    if not os.path.exists(seed_path):
        print(f"Seed file not found at {seed_path}")
        return

    try:
        with open(seed_path, "r") as f:
            rules = json.load(f)
            
        print(f"Found {len(rules)} seed rules. Ingesting...")
        
        for rule in rules:
            success = rag_manager.add_document(
                doc_type=rule["type"],
                title=rule["title"],
                content=rule["content"],
                tags=rule.get("tags"),
                source="seed_file",
                metadata=rule.get("metadata")
            )
            if success:
                print(f"[OK] Ingested: {rule['title']}")
            else:
                print(f"[FAILED] Ingested: {rule['title']}")
                
        print("Ingestion complete.")
    except Exception as e:
        print(f"Error during ingestion: {e}")

if __name__ == "__main__":
    ingest_seed()
