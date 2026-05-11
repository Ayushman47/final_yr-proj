import psutil

class ModelTier:
    LITE = "Lite"
    BALANCED = "Balanced"
    HIGH = "High Accuracy"

def get_recommended_tier() -> str:
    """Auto hardware detection to recommend a tier."""
    ram_gb = psutil.virtual_memory().total / (1024 ** 3)
    if ram_gb < 8:
        return ModelTier.LITE
    elif ram_gb >= 16:
        return ModelTier.HIGH
    else:
        return ModelTier.BALANCED

def get_tier_for_model(model_name: str) -> str:
    name = model_name.lower()
    if any(x in name for x in ["tiny", "phi", "mini"]):
        return ModelTier.LITE
    elif any(x in name for x in ["large", "deepseek", "70b"]):
        return ModelTier.HIGH
    else:
        return ModelTier.BALANCED

def get_tier_settings(tier: str) -> dict:
    if tier == ModelTier.LITE:
        return {
            "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
            "rerank": False,
            "top_k": 2,
            "max_history": 5,
            "temperature": 0.1,
            "chunk_size": 300,
            "chunk_overlap": 80
        }
    elif tier == ModelTier.HIGH:
        return {
            "embedding_model": "BAAI/bge-small-en-v1.5",
            "rerank": True,
            "top_k": 6,
            "max_history": 20,
            "temperature": 0.4,
            "chunk_size": 700,
            "chunk_overlap": 120
        }
    else: # Balanced
        return {
            "embedding_model": "BAAI/bge-small-en-v1.5",
            "rerank": True,
            "top_k": 4,
            "max_history": 10,
            "temperature": 0.3,
            "chunk_size": 500,
            "chunk_overlap": 100
        }
