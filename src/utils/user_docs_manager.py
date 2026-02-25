import os
import glob
import pickle
import hashlib
import time
import asyncio
import base64
from pathlib import Path
from typing import List, Dict, Any
import numpy as np
import openai
from aiohttp import ClientSession
from httpx_aiohttp import AiohttpTransport
from src.config.settings import settings
from src.utils.logging import setup_logger

logger = setup_logger(__name__)

# Qwen Embedding Configuration
QWEN_BASE_URL = settings.QWEN_BASE_URL
QWEN_API_KEY = settings.QWEN_API_KEY
QWEN_MODEL_NAME = "Qwen/Qwen3-Embedding-0.6B"
QWEN_DIMENSIONS = 1024


import asyncio
import httpx
import numpy as np
from google import genai
from google.genai import types

GEMINI_MODEL = "gemini-embedding-001"
GEMINI_DIM = 768

class GeminiEmbedder:
    def __init__(self, api_key: str, *, max_conns=500, max_keepalive=200):
        limits = httpx.Limits(
            max_connections=max_conns,
            max_keepalive_connections=max_keepalive,
            keepalive_expiry=60.0,
        )
        transport = httpx.AsyncHTTPTransport(retries=0)
        self._httpx = httpx.AsyncClient(limits=limits, transport=transport, timeout=60.0)

        http_options = types.HttpOptions(
            httpx_async_client=self._httpx,   # reuse pool
        )
        self._client = genai.Client(api_key=api_key, http_options=http_options)

    async def aclose(self):
        # docs: close async client explicitly
        await self._client.aio.aclose()
        await self._httpx.aclose()

    async def embed_texts(self, texts, *, subbatch_size=50, concurrency=32):
        sem = asyncio.Semaphore(concurrency)

        async def one_batch(batch):
            async with sem:
                resp = await self._client.aio.models.embed_content(
                    model=GEMINI_MODEL,
                    contents=batch,
                    config=types.EmbedContentConfig(
                        output_dimensionality=GEMINI_DIM,
                        task_type="CLUSTERING",
                    ),
                )
                # resp.embeddings is SDK-structured; normalize to np here
                return [np.array(e.values, dtype=np.float32) for e in resp.embeddings]

        tasks = [
            one_batch(texts[i:i+subbatch_size])
            for i in range(0, len(texts), subbatch_size)
        ]
        out = await asyncio.gather(*tasks)
        return [v for sub in out for v in sub]
    
gemini_embed = GeminiEmbedder(api_key=os.environ['GOOGLE_API_KEY'])
async def get_embeddings_for_texts_qwen(texts, subbatch_size=100):
    """
    Get embeddings for a list of texts using the Qwen embedding engine.
    Uses AiohttpTransport for optimal concurrent performance.
    """
    
    async def get_embeddings_subbatch(subbatch):
        """Process a single subbatch."""
        try:
            async with AiohttpTransport(client=ClientSession()) as aiohttp_transport:
                httpx_client = openai.DefaultAsyncHttpxClient(transport=aiohttp_transport)
                client = openai.AsyncOpenAI(
                    http_client=httpx_client, 
                    base_url=QWEN_BASE_URL,
                    api_key=QWEN_API_KEY, 
                    timeout=60
                )
                
                batch_embeddings = await client.embeddings.create(
                    input=subbatch,
                    model=QWEN_MODEL_NAME,
                    encoding_format="base64"
                )
                return batch_embeddings.data
        except Exception as e:
            logger.error(f"Subbatch failed: {e}")
            await asyncio.sleep(5)
            try:
                # Retry
                async with AiohttpTransport(client=ClientSession()) as aiohttp_transport:
                    httpx_client = openai.DefaultAsyncHttpxClient(transport=aiohttp_transport)
                    client = openai.AsyncOpenAI(
                        http_client=httpx_client, 
                        base_url=QWEN_BASE_URL,
                        api_key=QWEN_API_KEY, 
                        timeout=60
                    )
                    
                    batch_embeddings = await client.embeddings.create(
                        input=subbatch,
                        model=QWEN_MODEL_NAME,
                        encoding_format="base64"
                    )
                    return batch_embeddings.data
            except Exception as retry_e:
                logger.error(f"Subbatch retry failed: {retry_e}")
                # Return dummy embeddings to maintain structure
                return [type('obj', (object,), {'embedding': base64.b64encode(np.zeros(QWEN_DIMENSIONS, dtype=np.float32).tobytes()).decode()})() for _ in subbatch]

    # Create all subbatches
    tasks = []
    for i in range(0, len(texts), subbatch_size):
        subbatch = texts[i:i+subbatch_size]
        task = get_embeddings_subbatch(subbatch)
        tasks.append(task)
    
    logger.info(f"Processing {len(texts)} texts in {len(tasks)} subbatches concurrently via Qwen")
    
    start_time = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    processing_time = time.time() - start_time
    
    # Flatten results
    all_embeddings_data = []
    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Subbatch failed completely: {result}")
            continue
        all_embeddings_data.extend(result)
    
    logger.info(f"Completed Qwen embedding generation in {processing_time:.2f}s")

    # Decode base64 embeddings to numpy arrays
    embeddings = []
    for embedding_data in all_embeddings_data:
        base64_string = embedding_data.embedding
        decoded_bytes = base64.b64decode(base64_string)
        float_array = np.frombuffer(decoded_bytes, dtype=np.float32)
        embeddings.append(float_array)
        
    return embeddings

class UserDocsManager:
    """
    Manages user-facing documentation for tools.
    Uses Qwen embedding engine for persistence and search.
    """
    
    _instance = None
    CACHE_FILE = Path("docs/user_guides/vectors_qwen.pkl")
    DOCS_DIR = Path("docs/user_guides")
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(UserDocsManager, cls).__new__(cls)
            cls._instance.docs = []
            cls._instance.doc_vectors = None
            cls._instance.initialized = False
            cls._instance._lock = asyncio.Lock()
        return cls._instance

    async def initialize(self):
        """Load docs and embeddings (from disk or compute)."""
        if self.initialized:
            return

        async with self._lock:
            if self.initialized: # Double check
                return

            try:
                # Try to load from cache first
                if self._load_from_cache():
                    logger.info(f"Loaded {len(self.docs)} docs from Qwen vector cache.")
                else:
                    logger.info("Qwen cache miss or stale. Re-indexing documents...")
                    self._load_docs_from_files()
                    await self._embed_docs()
                    self._save_to_cache()
                
                self.initialized = True
                
            except Exception as e:
                logger.error(f"Failed to initialize UserDocsManager with Qwen: {e}", exc_info=True)

    def _calculate_dir_hash(self) -> str:
        """Calculate a hash of the docs directory state to detect changes."""
        hasher = hashlib.md5()
        
        # Hash user guides
        if self.DOCS_DIR.exists():
            files = sorted(list(self.DOCS_DIR.glob("*.md")))
            for p in files:
                hasher.update(str(p.name).encode())
                hasher.update(str(p.stat().st_mtime).encode())

        # Hash capabilities
        kb_dir = Path("docs/knowledge_base")
        if kb_dir.exists():
            files = sorted(list(kb_dir.glob("*.md")))
            for p in files:
                hasher.update(str(p.name).encode())
                hasher.update(str(p.stat().st_mtime).encode())
            
        return hasher.hexdigest()

    def _load_from_cache(self) -> bool:
        """Try to load docs and vectors from pickle."""
        if not self.CACHE_FILE.exists():
            return False
            
        try:
            with open(self.CACHE_FILE, 'rb') as f:
                data = pickle.load(f)
            
            current_hash = self._calculate_dir_hash()
            if data.get("hash") != current_hash:
                logger.info("Docs have changed. Invalidating Qwen cache.")
                return False
                
            self.docs = data["docs"]
            self.doc_vectors = data["vectors"]
            return True
        except Exception as e:
            logger.warning(f"Failed to load Qwen cache: {e}")
            return False

    def _save_to_cache(self):
        """Save docs and vectors to pickle."""
        try:
            data = {
                "hash": self._calculate_dir_hash(),
                "docs": self.docs,
                "vectors": self.doc_vectors
            }
            # Ensure parent directory exists
            self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(self.CACHE_FILE, 'wb') as f:
                pickle.dump(data, f)
            logger.info(f"Saved Qwen vector index to {self.CACHE_FILE}")
        except Exception as e:
            logger.error(f"Failed to save Qwen cache: {e}")

    def _load_docs_from_files(self):
        """Load markdown files from disk (Tools and Patterns)."""
        self.docs = []
        
        # 1. Load User Guides (Tools & Patterns)
        if self.DOCS_DIR.exists():
            for file_path in self.DOCS_DIR.glob("*.md"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # Determine type based on filename prefix
                        if file_path.name.startswith("patterns_"):
                            doc_type = "pattern"
                            # Strip 'patterns_' from ID for cleaner look
                            tool_id = file_path.stem.replace("patterns_", "")
                        else:
                            doc_type = "tool"
                            tool_id = file_path.stem.split('_', 1)[1] if '_' in file_path.stem else file_path.stem

                        self.docs.append({
                            "content": content,
                            "filename": file_path.name,
                            "type": doc_type,
                            "tool_id": tool_id
                        })
                except Exception as e:
                    logger.error(f"Error loading doc {file_path}: {e}")
        
        # 2. Load Capabilities (High-Level Overview)
        kb_dir = Path("docs/knowledge_base")
        if kb_dir.exists():
            for file_path in kb_dir.glob("*.md"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        self.docs.append({
                            "content": content,
                            "filename": file_path.name,
                            "type": "capability",
                            "tool_id": f"capability:{file_path.stem}" # Pseudo-ID
                        })
                except Exception as e:
                    logger.error(f"Error loading capability doc {file_path}: {e}")
            
            logger.info(f"Loaded {len(self.docs)} total documents (Tools + Capabilities).")

    async def _embed_docs(self):
        """Compute embeddings for all docs using Qwen engine."""
        if not self.docs:
            return

        texts = [d["content"] for d in self.docs]
        try:
            vectors = await gemini_embed.embed_texts(texts)
            self.doc_vectors = np.array(vectors)
        except Exception as e:
            logger.error(f"Error embedding documents with Qwen: {e}")

    async def search(self, query: str, top_k_tools: int = 3, top_k_patterns: int = 3, top_k_caps: int = 2) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search for relevant user guides, ensuring representation from all categories.
        
        Returns:
            Dictionary with keys 'tools', 'patterns', 'capabilities'.
        """
        if not self.initialized:
            await self.initialize()
            
        if self.doc_vectors is None or len(self.docs) == 0:
            return {"tools": [], "patterns": [], "capabilities": []}

        try:
            # Embed the query
            query_embeddings = await gemini_embed.embed_texts([query])
            if not query_embeddings:
                return {"tools": [], "patterns": [], "capabilities": []}
            
            query_vector = query_embeddings[0]
            
            # Compute similarity for ALL docs
            scores = np.dot(self.doc_vectors, query_vector)
            
            # Helper to get top K for a specific type
            def get_top_k_for_type(doc_type, k):
                # Get indices where type matches
                type_indices = [i for i, d in enumerate(self.docs) if d.get('type', 'tool') == doc_type] # default to tool for backward compat
                
                if not type_indices:
                    return []
                
                # Get scores for these indices
                type_scores = scores[type_indices]
                
                # Get top K indices relative to the type_scores array
                if len(type_scores) == 0: 
                    return []
                    
                # top k argsort
                # if k > len, just take all
                effective_k = min(k, len(type_scores))
                top_local_indices = np.argsort(type_scores)[-effective_k:][::-1]
                
                results = []
                for local_idx in top_local_indices:
                    original_idx = type_indices[local_idx]
                    score = float(scores[original_idx])
                    doc = self.docs[original_idx].copy()
                    doc["score"] = score
                    results.append(doc)
                return results

            # Perform categorized retrieval
            return {
                "tools": get_top_k_for_type('tool', top_k_tools),
                "patterns": get_top_k_for_type('pattern', top_k_patterns),
                "capabilities": get_top_k_for_type('capability', top_k_caps)
            }

        except Exception as e:
            logger.error(f"Error searching user guides with Qwen: {e}", exc_info=True)
            return {"tools": [], "patterns": [], "capabilities": []}

# Global instance
user_docs_manager = UserDocsManager()