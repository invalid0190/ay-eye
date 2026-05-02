import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.rag.rag_manager import rag_manager
from core.utils.logger import logger

def test_rag():
    print("--- RAG Testing Started ---")
    
    # 1. Search for Blender rule
    print("\n[Test 1] Searching for 'Blender import menu click'...")
    results = rag_manager.search("Blender import menu click")
    found_blender = False
    for res in results:
        print(f"  - Found: {res['title']} ({res['type']})")
        if "blender" in res['content'].lower():
            found_blender = True
            
    if found_blender:
        print("  [OK] SUCCESS: Blender rule retrieved.")
    else:
        print("  [FAILED] FAILURE: Blender rule not found.")

    # 2. Search for dangerous command rule
    print("\n[Test 2] Searching for 'dangerous command'...")
    results = rag_manager.search("dangerous command")
    found_safety = False
    for res in results:
        print(f"  - Found: {res['title']} ({res['type']})")
        if "destructive" in res['content'].lower() or "safety" in res['type']:
            found_safety = True
            
    if found_safety:
        print("  [OK] SUCCESS: Safety rule retrieved.")
    else:
        print("  [FAILED] FAILURE: Safety rule not found.")

    # 3. Build context test
    print("\n[Test 3] Building context for 'import file in blender'...")
    context = rag_manager.build_context("import file in blender", active_app="Blender")
    if "RELEVANT MEMORY" in context and "blender" in context.lower():
        print("  [OK] SUCCESS: Context built with relevant Blender info.")
        # print(context)
    else:
        print("  [FAILED] FAILURE: Context build failed or irrelevant.")

    print("\n--- RAG Testing Complete ---")

if __name__ == "__main__":
    test_rag()
