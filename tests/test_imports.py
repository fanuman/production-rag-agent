# tests/test_imports.py
import importlib

MODULES = [
    "src.core.config", "src.core.embeddings", "src.core.vectorstore", "src.core.llm_client",
    "src.tools.inventory_tool", "src.rag.prompts", "src.rag.pipeline",
    "src.evaluation.prompts", "src.evaluation.metrics", "src.api.models", "src.api.main",
]

def test_all_modules_import():
    for module_name in MODULES:
        importlib.import_module(module_name)