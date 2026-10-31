from tg_msg_checker.config import Settings
from tg_msg_checker.models import Message
from tg_msg_checker.pipeline import AnalysisEngine


def test_parallel_matches_inline(tmp_path):
    settings = Settings(workers=2, coord_crs="sk42")
    engine = AnalysisEngine(tmp_path, settings)
    engine.create_dictionary("Зброя", "uk", "weapon", ["граната"])
    engine.start_pool()
    try:
        filler = "а" * 5000
        messages = [Message(str(index), f"гранату {filler}") for index in range(8)]
        inline = engine.analyze(messages, parallel=False)
        parallel = engine.analyze(messages, parallel=True)
        assert inline == parallel
        assert [item["id"] for item in inline] == [str(index) for index in range(8)]
        assert inline[0]["tags"][0]["matches"][0]["lemma"] == "граната"
    finally:
        engine.shutdown()
