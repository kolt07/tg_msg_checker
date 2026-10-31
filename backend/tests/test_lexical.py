from tg_msg_checker.analyzers.lexical import LexicalAnalyzer
from tg_msg_checker.lemmatize import build_form_index
from tg_msg_checker.models import Dictionary


def _analyzer(language: str, tag: str, words: list[str]) -> tuple[LexicalAnalyzer, dict]:
    entry = Dictionary(id="dict-1", name="Тест", language=language, tag=tag, words=words)
    forms, stats = build_form_index([entry])
    return LexicalAnalyzer(forms), forms


def test_ukrainian_inflection_and_boundary():
    analyzer, forms = _analyzer("uk", "weapon", ["граната"])
    assert "гранату" in forms
    found = analyzer.analyze("бачив гранату, і все")
    assert len(found) == 1
    assert found[0].name == "weapon"
    assert found[0].text == "гранату"
    assert found[0].payload["lemma"] == "граната"
    assert found[0].start == 6
    assert analyzer.analyze("гранатуха") == []


def test_russian_inflection():
    analyzer, forms = _analyzer("ru", "air", ["вертолёт"])
    assert "вертолёта" in forms
    found = analyzer.analyze("нет вертолёта")
    assert len(found) == 1
    assert found[0].payload["lemma"] == "вертолёт"
    assert found[0].text == "вертолёта"


def test_english_inflection():
    analyzer, forms = _analyzer("en", "weapon", ["grenade"])
    assert "grenades" in forms
    found = analyzer.analyze("two grenades nearby")
    assert len(found) == 1
    assert found[0].text == "grenades"
    assert found[0].payload["lemma"] == "grenade"


def test_ukrainian_phrase():
    analyzer, forms = _analyzer("uk", "vehicle", ["бойова машина"])
    assert "бойову машину" in forms
    found = analyzer.analyze("бачив бойову машину вчора")
    assert any(item.payload["lemma"] == "бойова машина" and "машину" in item.text for item in found)


def test_same_form_two_tags():
    entries = [
        Dictionary(id="a", name="A", language="uk", tag="one", words=["граната"]),
        Dictionary(id="b", name="B", language="uk", tag="two", words=["граната"]),
    ]
    forms, _stats = build_form_index(entries)
    found = LexicalAnalyzer(forms).analyze("гранату")
    assert {item.name for item in found} == {"one", "two"}
