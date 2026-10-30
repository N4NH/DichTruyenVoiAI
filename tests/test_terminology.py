import tempfile
from pathlib import Path
from src.processors.terminology import GlossaryManager, GlossaryEntry, TerminologyExtractor

def test_glossary_save_and_load():
    with tempfile.TemporaryDirectory() as tmpdir:
        file_path = Path(tmpdir) / "glossary.txt"
        entries = [
            GlossaryEntry(term="Kirito", translation="Ki-ri-to", category="CHARACTERS", note="Main character"),
            GlossaryEntry(term="Aincrad", translation="Aincrad", category="LOCATIONS", note="Floating castle")
        ]
        manager = GlossaryManager(entries)
        manager.save(file_path)

        loaded = GlossaryManager.load(file_path)
        assert len(loaded.entries) == 2
        assert loaded.entries[0].term == "Kirito"
        assert loaded.entries[0].translation == "Ki-ri-to"
        assert loaded.entries[1].term == "Aincrad"

def test_extract_candidates():
    extractor = TerminologyExtractor()
    texts = [
        "Rimuru Tempest went to the Great Jura Forest.",
        "Rimuru Tempest met with Veldora."
    ]
    candidates = extractor.extract_candidates(texts, min_frequency=2)
    assert "Rimuru Tempest" in candidates
    assert candidates["Rimuru Tempest"] == 2

