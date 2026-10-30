import pytest
from src.processors.chunker import SmartChunker

def test_chunker_short_text():
    chunker = SmartChunker(threshold=100, target_chunk_size=50)
    text = "Đây là một đoạn văn ngắn."
    chunks = chunker.split(text)
    assert len(chunks) == 1
    assert chunks[0].content == text
    assert chunks[0].index == 1
    assert chunks[0].total == 1

def test_chunker_long_text_split():
    chunker = SmartChunker(threshold=100, target_chunk_size=50)
    # Text longer than threshold
    text = (
        "Đoạn văn thứ nhất dài vừa đủ để kiểm tra.\n\n"
        "Đoạn văn thứ hai tiếp nối câu chuyện một cách tự nhiên.\n\n"
        "Đoạn văn thứ ba kết thúc chương truyện này."
    )
    chunks = chunker.split(text)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert len(chunk.content) > 0
        assert chunk.total == len(chunks)

def test_chunker_empty_text():
    chunker = SmartChunker()
    assert chunker.split("") == []
    assert chunker.split("   ") == []

