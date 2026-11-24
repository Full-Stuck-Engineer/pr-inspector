"""Unit tests for PythonAstChunker (Issue #17)."""

from pr_inspector.domain.entities import ChunkType
from pr_inspector.infrastructure.indexer.ast_chunker import PythonAstChunker

SAMPLE_PYTHON_CODE = '''"""Sample module docstring."""

import os
from typing import Any

GLOBAL_TIMEOUT = 30


def calculate_metrics(values: list[int]) -> float:
    """Calculate average metric."""
    if not values:
        return 0.0
    return sum(values) / len(values)


async def async_fetch_data(endpoint: str) -> dict[str, Any]:
    """Fetch data asynchronously."""
    return {"endpoint": endpoint}


class AnalysisService:
    """Service performing analysis."""

    def __init__(self, name: str) -> None:
        self.name = name

    def execute(self) -> bool:
        """Run execution."""
        return True


class SimpleConfig:
    retries: int = 3
    timeout: float = 5.0
'''


def test_chunk_python_ast_structure():
    chunker = PythonAstChunker()
    chunks = chunker.chunk_file("src/service.py", SAMPLE_PYTHON_CODE)

    # 1. Module preamble
    preamble = [c for c in chunks if c.chunk_type == ChunkType.MODULE_PREAMBLE]
    assert len(preamble) == 1
    assert "GLOBAL_TIMEOUT" in preamble[0].content
    assert preamble[0].start_line == 1

    # 2. Synchronous function
    func_chunk = next(c for c in chunks if c.symbol_name == "calculate_metrics")
    assert func_chunk.chunk_type == ChunkType.FUNCTION
    assert "def calculate_metrics" in func_chunk.content
    assert func_chunk.language == "python"

    # 3. Asynchronous function
    async_chunk = next(c for c in chunks if c.symbol_name == "async_fetch_data")
    assert async_chunk.chunk_type == ChunkType.FUNCTION
    assert "async def async_fetch_data" in async_chunk.content

    # 4. Class header
    class_chunks = [
        c for c in chunks if c.symbol_name == "AnalysisService" and c.chunk_type == ChunkType.CLASS
    ]
    assert len(class_chunks) == 1
    class_chunk = class_chunks[0]
    assert "class AnalysisService:" in class_chunk.content
    assert "Service performing analysis" in class_chunk.content

    # 5. Methods with parent symbol
    init_chunks = [
        c for c in chunks if c.symbol_name == "__init__" and c.parent_symbol == "AnalysisService"
    ]
    assert len(init_chunks) == 1
    init_chunk = init_chunks[0]
    assert init_chunk.chunk_type == ChunkType.METHOD
    assert "def __init__" in init_chunk.content

    exec_chunks = [
        c for c in chunks if c.symbol_name == "execute" and c.parent_symbol == "AnalysisService"
    ]
    assert len(exec_chunks) == 1
    exec_chunk = exec_chunks[0]
    assert exec_chunk.chunk_type == ChunkType.METHOD
    assert "def execute" in exec_chunk.content
    assert exec_chunk.chunk_type == ChunkType.METHOD
    assert "def execute" in exec_chunk.content

    # 6. Class without methods (pure dataclass/enum/config)
    config_chunk = next(c for c in chunks if c.symbol_name == "SimpleConfig")
    assert config_chunk.chunk_type == ChunkType.CLASS
    assert "class SimpleConfig:" in config_chunk.content


def test_chunk_empty_python_file():
    chunker = PythonAstChunker()
    assert chunker.chunk_file("empty.py", "") == []
    assert chunker.chunk_file("whitespace.py", "   \n\n  \t  ") == []


def test_chunk_syntax_error_fallback():
    chunker = PythonAstChunker()
    broken_code = "def invalid_syntax(a, b\n    return a +"
    chunks = chunker.chunk_file("broken.py", broken_code)

    assert len(chunks) == 1
    assert chunks[0].chunk_type == ChunkType.TEXT_BLOCK
    assert chunks[0].content == broken_code
    assert chunks[0].start_line == 1
    assert chunks[0].end_line == 2
