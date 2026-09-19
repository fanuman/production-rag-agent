# src/core/semantic_cache.py
import redis
import numpy as np
import time
import uuid
import os
from redis.commands.search.field import TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
from redis.commands.search.query import Query

EMBEDDING_DIM = 1536  # text-embedding-3-small


class SemanticCache:
    def __init__(self, host=None, port=6379, threshold=0.05, ttl_seconds=3600):
        host = host or os.getenv("REDIS_HOST", "redis")  # "redis" = Compose default; ECS overrides to "localhost"
        self.client = redis.Redis(host=host, port=port, decode_responses=False)
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds
        self._ensure_index()

    def _ensure_index(self):
        try:
            self.client.ft("cache_idx").info()
            return  # already exists
        except redis.exceptions.ResponseError:
            pass
        schema = (
            TextField("prompt"),
            TextField("response"),
            TextField("full_context"),
            VectorField("embedding", "FLAT", {
                "TYPE": "FLOAT32", "DIM": EMBEDDING_DIM, "DISTANCE_METRIC": "COSINE"
            }),
        )
        self.client.ft("cache_idx").create_index(
            schema, definition=IndexDefinition(prefix=["cache:"], index_type=IndexType.HASH)
        )

    def check(self, query_embedding):
        vector_bytes = np.array(query_embedding, dtype=np.float32).tobytes()
        q = (Query("*=>[KNN 1 @embedding $vec AS distance]")
            .sort_by("distance").return_fields("response", "full_context", "distance")
            .dialect(2))
        results = self.client.ft("cache_idx").search(q, query_params={"vec": vector_bytes})
        
        if results.docs and float(results.docs[0].distance) <= self.threshold:
            return {"response": results.docs[0].response, "full_context": results.docs[0].full_context}
        return None

    def store(self, prompt, response, query_embedding, full_context=""):
        key = f"cache:{uuid.uuid4().hex}"
        self.client.hset(key, mapping={
            "prompt": prompt,
            "response": response,
            "full_context": full_context,
            "embedding": np.array(query_embedding, dtype=np.float32).tobytes(),
            "created_ts": int(time.time()),
        })
        self.client.expire(key, self.ttl_seconds)