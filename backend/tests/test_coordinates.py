import mgrs
import pytest
from pyproj import Transformer

from tg_msg_checker.analyzers.coordinates import CoordinateAnalyzer

GK = "X = 5179365 Y = 6500127"


def test_gauss_kruger_fixture_projects_near_zone_axis():
    found = CoordinateAnalyzer("sk42").analyze(f"точка {GK} кінець")
    assert len(found) == 1
    payload = found[0].payload
    assert payload["format"] == "gauss_kruger"
    assert found[0].text == GK
    assert payload["lat"] == pytest.approx(46.6, abs=0.3)
    assert payload["lon"] == pytest.approx(33.0, abs=0.05)


def test_gauss_kruger_variants_and_usk2000():
    samples = [
        "X=5179365, Y=6500127",
        "Y = 6500127 X = 5179365",
        "Х = 5179365 У = 6500127",
        "X = 5 179 365 Y = 6 500 127",
        "X = 5179365.5 Y = 6500127.25",
    ]
    for text in samples:
        found = CoordinateAnalyzer().analyze(text)
        assert found, text
        assert found[0].payload["format"] == "gauss_kruger"
        assert found[0].payload["lon"] == pytest.approx(33.0, abs=0.05)

    sk42 = CoordinateAnalyzer("sk42").analyze(GK)[0].payload
    usk = CoordinateAnalyzer("usk2000").analyze(GK)[0].payload
    assert usk["lat"] == pytest.approx(sk42["lat"], abs=0.01)
    assert usk["lon"] == pytest.approx(sk42["lon"], abs=0.01)


def test_bare_gauss_kruger_comma_pair_when_it_projects():
    found = CoordinateAnalyzer().analyze("точка 5158697, 6485198 кінець")
    assert len(found) == 1
    assert found[0].text == "5158697, 6485198"
    assert found[0].payload["format"] == "gauss_kruger"
    assert found[0].payload["lat"] == pytest.approx(46.562, abs=0.01)
    assert found[0].payload["lon"] == pytest.approx(32.805, abs=0.01)

    compact = CoordinateAnalyzer().analyze("5158697,6485198")
    assert compact[0].text == "5158697,6485198"
    spaced = CoordinateAnalyzer().analyze("5 158 697, 6 485 198")
    assert spaced[0].payload["lat"] == pytest.approx(found[0].payload["lat"], abs=1e-4)


def test_gauss_kruger_rejects_invalid_and_unseparated_numbers():
    analyzer = CoordinateAnalyzer()
    assert analyzer.analyze("5179365 6500127") == []
    assert analyzer.analyze("X = 20000000 Y = 6500127") == []
    assert analyzer.analyze("X = 5179365 Y = 6900000") == []
    assert analyzer.analyze("X = 5179365") == []
    assert analyzer.analyze("5158697, 100") == []
    assert analyzer.analyze("20000000, 6485198") == []


def test_decimal_dms_and_ddm():
    analyzer = CoordinateAnalyzer()
    decimal = analyzer.analyze("точка 50.4501, 30.5234.")
    assert len(decimal) == 1
    assert decimal[0].payload["format"] == "decimal"
    assert decimal[0].payload["lat"] == pytest.approx(50.4501)
    assert decimal[0].payload["lon"] == pytest.approx(30.5234)

    labeled = analyzer.analyze("широта 50.45, довгота 30.52")
    assert labeled[0].payload["format"] == "decimal"
    assert labeled[0].payload["lat"] == pytest.approx(50.45)
    assert labeled[0].payload["lon"] == pytest.approx(30.52)

    south = analyzer.analyze("місто -33.8688, 151.2093")
    assert south[0].payload["lat"] == pytest.approx(-33.8688)
    assert south[0].payload["lon"] == pytest.approx(151.2093)

    dms = analyzer.analyze("50°27'00\"N 30°31'24\"E")
    assert len(dms) == 1
    assert dms[0].payload["format"] == "dms"
    assert dms[0].payload["lat"] == pytest.approx(50.45, abs=1e-4)
    assert dms[0].payload["lon"] == pytest.approx(30 + 31 / 60 + 24 / 3600, abs=1e-5)

    ddm = analyzer.analyze("50°27.0'N 30°31.4'E")
    assert ddm[0].payload["format"] == "ddm"
    assert ddm[0].payload["lat"] == pytest.approx(50.45, abs=1e-6)
    assert ddm[0].payload["lon"] == pytest.approx(30 + 31.4 / 60, abs=1e-6)

    assert analyzer.analyze("широта 95.0 довгота 30.0") == []
    assert analyzer.analyze("просто 50, 30 без дробу") == []


def test_decimal_does_not_override_longer_dms():
    found = CoordinateAnalyzer().analyze("50°27'00.36\"N 30°31'24.24\"E")
    assert [item.payload["format"] for item in found] == ["dms"]


def test_utm_and_mgrs_roundtrip():
    transformer = Transformer.from_crs(
        "EPSG:4326",
        "+proj=utm +zone=36 +north +datum=WGS84 +units=m +no_defs",
        always_xy=True,
    )
    easting, northing = transformer.transform(30.5234, 50.4501)
    utm_text = f"зона 36U {int(round(easting))} {int(round(northing))} далі"
    utm = [item for item in CoordinateAnalyzer().analyze(utm_text) if item.payload["format"] == "utm"]
    assert len(utm) == 1
    assert utm[0].payload["lat"] == pytest.approx(50.4501, abs=0.002)
    assert utm[0].payload["lon"] == pytest.approx(30.5234, abs=0.002)

    encoded = mgrs.MGRS().toMGRS(50.4501, 30.5234)
    if isinstance(encoded, bytes):
        encoded = encoded.decode("ascii")
    mgrs_hits = [
        item
        for item in CoordinateAnalyzer().analyze(f"квадрат {encoded} кінець")
        if item.payload["format"] == "mgrs"
    ]
    assert len(mgrs_hits) == 1
    assert mgrs_hits[0].payload["lat"] == pytest.approx(50.4501, abs=0.01)
    assert mgrs_hits[0].payload["lon"] == pytest.approx(30.5234, abs=0.01)


def test_mixed_formats_keep_both_when_they_do_not_overlap():
    text = "50.4501, 30.5234 та X = 5179365 Y = 6500127"
    formats = {item.payload["format"] for item in CoordinateAnalyzer().analyze(text)}
    assert formats == {"decimal", "gauss_kruger"}
