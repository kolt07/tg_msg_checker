from __future__ import annotations

import math
import re
from functools import lru_cache

from pyproj import Transformer

from tg_msg_checker.models import Finding

# X — північ, Y — схід. У записі з номером зони хибний схід уже містить зону:
# для зони 6 це 6_500_000, тож у проєкцію йде повне Y.
_GK_LABEL = r"[XxYyХхУу]"
_GK_NUMBER = r"[+-]?(?:\d{1,3}(?:[ \u00A0\u202F]\d{3})+|\d+)(?:[.,]\d+)?"
_GK_GAP = r"[\s,;]{0,40}"
_GK_RE = re.compile(
    rf"(?<![\w])(?P<l1>{_GK_LABEL})\s*[=:]\s*(?P<n1>{_GK_NUMBER})"
    rf"{_GK_GAP}(?P<l2>{_GK_LABEL})\s*[=:]\s*(?P<n2>{_GK_NUMBER})(?!\d)"
)

_DEG = r"[°º]"
_MIN = r"['\u2032\u2019]"
_SEC = r'(?:["\u2033\u201d]|\'\')'
_HEMI = r"[NnSsEeWw]"
_DMS_PART = (
    rf"(\d{{1,3}})\s*{_DEG}\s*(\d{{1,2}})\s*{_MIN}\s*"
    rf"(\d{{1,2}}(?:[.,]\d+)?)\s*{_SEC}\s*({_HEMI})"
)
_DMS_RE = re.compile(rf"(?<![\w]){_DMS_PART}\s*[,;/]?\s*{_DMS_PART}(?![\w])")
_DDM_PART = rf"(\d{{1,3}})\s*{_DEG}\s*(\d{{1,2}}(?:[.,]\d+)?)\s*{_MIN}\s*({_HEMI})"
_DDM_RE = re.compile(rf"(?<![\w]){_DDM_PART}\s*[,;/]?\s*{_DDM_PART}(?![\w])")

_DEC_NUM = r"[+-]?\d{1,3}(?:[.,]\d+)?"
_FRAC_DOT = r"[+-]?\d{1,3}\.\d+"
_FRAC_COM = r"[+-]?\d{1,3},\d+"
_LAT_WORD = r"latitude|lat|широта|шир|ш\."
_LON_WORD = r"longitude|long|lon|довгота|довг|д\."
_LABELED_LAT_LON = re.compile(
    rf"(?<![\w])(?i:{_LAT_WORD})\s*[:=]?\s*({_DEC_NUM})\s*{_DEG}?"
    rf"[\s,;/]{{0,40}}(?i:{_LON_WORD})\s*[:=]?\s*({_DEC_NUM})\s*{_DEG}?(?![\w])"
)
_LABELED_LON_LAT = re.compile(
    rf"(?<![\w])(?i:{_LON_WORD})\s*[:=]?\s*({_DEC_NUM})\s*{_DEG}?"
    rf"[\s,;/]{{0,40}}(?i:{_LAT_WORD})\s*[:=]?\s*({_DEC_NUM})\s*{_DEG}?(?![\w])"
)
_HEMI_SUFFIX = re.compile(
    rf"(?<![\w])({_DEC_NUM})\s*{_DEG}?\s*([NnSs])\s*[,;/]?\s*"
    rf"({_DEC_NUM})\s*{_DEG}?\s*([EeWw])(?![\w])"
    rf"|(?<![\w])({_DEC_NUM})\s*{_DEG}?\s*([EeWw])\s*[,;/]?\s*"
    rf"({_DEC_NUM})\s*{_DEG}?\s*([NnSs])(?![\w])"
)
_HEMI_PREFIX = re.compile(
    rf"(?<![\w])([NnSs])\s*({_DEC_NUM})\s*{_DEG}?\s*[,;/]?\s*"
    rf"([EeWw])\s*({_DEC_NUM})\s*{_DEG}?(?![\w])"
    rf"|(?<![\w])([EeWw])\s*({_DEC_NUM})\s*{_DEG}?\s*[,;/]?\s*"
    rf"([NnSs])\s*({_DEC_NUM})\s*{_DEG}?(?![\w])"
)
_UNLABELED_DOT = re.compile(
    rf"(?<![\w])({_FRAC_DOT})(?:\s*[,;]\s*|\s+)({_FRAC_DOT})(?![\w])"
)
_UNLABELED_COM = re.compile(
    rf"(?<![\w])({_FRAC_COM})(?:\s*;\s*|\s+|,\s+)({_FRAC_COM})(?![\w])"
)

_UTM_RE = re.compile(
    r"(?<![\w])(\d{1,2})\s*([C-HJ-NP-Xc-hj-np-x])\s+(\d{6})\s+(\d{6,8})(?!\d)"
)
_MGRS_RE = re.compile(
    r"(?<!\w)(\d{1,2})\s*([C-HJ-NP-X])\s*([A-HJ-NP-Z]{2})\s*((?:\d\s*){2,10})(?!\d)",
    re.IGNORECASE,
)

_SOUTH_BANDS = set("CDEFGHJKLM")
_NORTH_BANDS = set("NPQRTUVWX")
_FORMAT_PRIORITY = {
    "gauss_kruger": 0,
    "dms": 1,
    "ddm": 2,
    "mgrs": 3,
    "utm": 4,
    "decimal": 5,
}

_SK42_TOWGS84 = "23.92,-141.27,-80.9,0,-0.35,-0.82,-0.12"
_USK2000_TOWGS84 = "24,-121,-76,0,0,0,0"


def _on_earth(lat: float, lon: float) -> bool:
    return math.isfinite(lat) and math.isfinite(lon) and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def _norm_lon(lon: float) -> float:
    return ((lon + 180.0) % 360.0) - 180.0


def _angle_distance(left: float, right: float) -> float:
    return abs(_norm_lon(left - right))


def _parse_float(raw: str) -> float | None:
    cleaned = (
        raw.replace(" ", "")
        .replace("\u00a0", "")
        .replace("\u202f", "")
        .replace(",", ".")
    )
    if cleaned.count(".") > 1:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return value


def _apply_hemi(value: float, hemi: str) -> float:
    magnitude = abs(value)
    if hemi.upper() in {"S", "W"}:
        return -magnitude
    return magnitude


def _axis(label: str) -> str | None:
    if label in "XxХх":
        return "x"
    if label in "YyУу":
        return "y"
    return None


@lru_cache(maxsize=128)
def _gk_transformer(zone: int, crs_name: str) -> Transformer:
    central = 6 * zone - 3
    false_easting = zone * 1_000_000 + 500_000
    towgs84 = _USK2000_TOWGS84 if crs_name == "usk2000" else _SK42_TOWGS84
    proj = (
        f"+proj=tmerc +lat_0=0 +lon_0={central} +k=1 +x_0={false_easting} +y_0=0 "
        f"+ellps=krass +towgs84={towgs84} +units=m +no_defs"
    )
    return Transformer.from_crs(proj, "EPSG:4326", always_xy=True)


@lru_cache(maxsize=128)
def _utm_transformer(zone: int, hemisphere: str) -> Transformer:
    proj = f"+proj=utm +zone={zone} +{hemisphere} +datum=WGS84 +units=m +no_defs"
    return Transformer.from_crs(proj, "EPSG:4326", always_xy=True)


def _utm_hemisphere(letter: str) -> str | None:
    band = letter.upper()
    # N/S у записі на кшталт «36N 412345 5678901» — півкуля GPS.
    # Решта літер — смуги сітки, півкуля випливає зі смуги.
    if band == "N":
        return "north"
    if band == "S":
        return "south"
    if band in _SOUTH_BANDS:
        return "south"
    if band in _NORTH_BANDS:
        return "north"
    return None


class CoordinateAnalyzer:
    def __init__(self, crs: str = "sk42"):
        self.crs = crs if crs in {"sk42", "usk2000"} else "sk42"
        self._mgrs = None

    def analyze(self, text: str) -> list[Finding]:
        if not text:
            return []
        found: list[Finding] = []
        found.extend(self._gauss_kruger(text))
        found.extend(self._angular(text, _DMS_RE, "dms", with_seconds=True))
        found.extend(self._angular(text, _DDM_RE, "ddm", with_seconds=False))
        found.extend(self._labeled_decimal(text))
        found.extend(self._hemisphere_decimal(text))
        found.extend(self._unlabeled_decimal(text))
        found.extend(self._utm(text))
        found.extend(self._mgrs_hits(text))
        return _resolve_overlaps(found)

    def _hit(self, text: str, start: int, end: int, fmt: str, lat: float, lon: float) -> Finding | None:
        start, end = _tighten(text, start, end)
        if start >= end or not _on_earth(lat, lon):
            return None
        return Finding(
            kind="entity",
            name="coordinates",
            text=text[start:end],
            start=start,
            end=end,
            payload={"format": fmt, "lat": round(lat, 6), "lon": round(lon, 6)},
        )

    def _gauss_kruger(self, text: str) -> list[Finding]:
        found: list[Finding] = []
        for match in _GK_RE.finditer(text):
            first_axis = _axis(match.group("l1"))
            second_axis = _axis(match.group("l2"))
            first = _parse_float(match.group("n1"))
            second = _parse_float(match.group("n2"))
            if first is None or second is None:
                continue
            if first_axis == "x" and second_axis == "y":
                northing, easting = first, second
            elif first_axis == "y" and second_axis == "x":
                easting, northing = first, second
            else:
                continue
            converted = _project_gk(northing, easting, self.crs)
            if converted is None:
                continue
            lat, lon = converted
            hit = self._hit(text, match.start(), match.end(), "gauss_kruger", lat, lon)
            if hit is not None:
                found.append(hit)
        return found

    def _angular(self, text: str, pattern: re.Pattern[str], fmt: str, with_seconds: bool) -> list[Finding]:
        found: list[Finding] = []
        for match in pattern.finditer(text):
            if with_seconds:
                left = _signed_dms(match.group(1), match.group(2), match.group(3), match.group(4))
                right = _signed_dms(match.group(5), match.group(6), match.group(7), match.group(8))
            else:
                left = _signed_ddm(match.group(1), match.group(2), match.group(3))
                right = _signed_ddm(match.group(4), match.group(5), match.group(6))
            if left is None or right is None:
                continue
            paired = _pair_signed(left, right)
            if paired is None:
                continue
            lat, lon = paired
            hit = self._hit(text, match.start(), match.end(), fmt, lat, lon)
            if hit is not None:
                found.append(hit)
        return found

    def _labeled_decimal(self, text: str) -> list[Finding]:
        found: list[Finding] = []
        for match in _LABELED_LAT_LON.finditer(text):
            lat = _parse_float(match.group(1))
            lon = _parse_float(match.group(2))
            if lat is None or lon is None:
                continue
            hit = self._hit(text, match.start(), match.end(), "decimal", lat, lon)
            if hit is not None:
                found.append(hit)
        for match in _LABELED_LON_LAT.finditer(text):
            lon = _parse_float(match.group(1))
            lat = _parse_float(match.group(2))
            if lat is None or lon is None:
                continue
            hit = self._hit(text, match.start(), match.end(), "decimal", lat, lon)
            if hit is not None:
                found.append(hit)
        return found

    def _hemisphere_decimal(self, text: str) -> list[Finding]:
        found: list[Finding] = []
        for pattern, order in ((_HEMI_SUFFIX, "value-hemi"), (_HEMI_PREFIX, "hemi-value")):
            for match in pattern.finditer(text):
                groups = [group for group in match.groups() if group is not None]
                if len(groups) != 4:
                    continue
                if order == "value-hemi":
                    paired = _pair_values(groups[0], groups[1], groups[2], groups[3])
                else:
                    paired = _pair_values(groups[1], groups[0], groups[3], groups[2])
                if paired is None:
                    continue
                lat, lon = paired
                hit = self._hit(text, match.start(), match.end(), "decimal", lat, lon)
                if hit is not None:
                    found.append(hit)
        return found

    def _unlabeled_decimal(self, text: str) -> list[Finding]:
        found: list[Finding] = []
        for pattern in (_UNLABELED_DOT, _UNLABELED_COM):
            for match in pattern.finditer(text):
                lat = _parse_float(match.group(1))
                lon = _parse_float(match.group(2))
                if lat is None or lon is None:
                    continue
                hit = self._hit(text, match.start(), match.end(), "decimal", lat, lon)
                if hit is not None:
                    found.append(hit)
        return found

    def _utm(self, text: str) -> list[Finding]:
        found: list[Finding] = []
        for match in _UTM_RE.finditer(text):
            zone = int(match.group(1))
            hemisphere = _utm_hemisphere(match.group(2))
            easting = int(match.group(3))
            northing = int(match.group(4))
            if hemisphere is None or not 1 <= zone <= 60:
                continue
            if not 100_000 <= easting <= 900_000 or not 0 <= northing <= 10_000_000:
                continue
            try:
                lon, lat = _utm_transformer(zone, hemisphere).transform(easting, northing)
            except Exception:
                continue
            hit = self._hit(text, match.start(), match.end(), "utm", lat, lon)
            if hit is not None:
                found.append(hit)
        return found

    def _mgrs_hits(self, text: str) -> list[Finding]:
        found: list[Finding] = []
        for match in _MGRS_RE.finditer(text):
            compact = _compact_mgrs(match)
            if compact is None:
                continue
            converted = self._mgrs_to_latlon(compact)
            if converted is None:
                continue
            lat, lon = converted
            hit = self._hit(text, match.start(), match.end(), "mgrs", lat, lon)
            if hit is not None:
                found.append(hit)
        return found

    def _mgrs_to_latlon(self, compact: str) -> tuple[float, float] | None:
        if self._mgrs is None:
            import mgrs

            self._mgrs = mgrs.MGRS()
        try:
            latlon = self._mgrs.toLatLon(compact)
        except Exception:
            try:
                latlon = self._mgrs.toLatLon(compact.encode("ascii"))
            except Exception:
                return None
        try:
            lat = float(latlon[0])
            lon = float(latlon[1])
        except (TypeError, ValueError, IndexError):
            return None
        if not _on_earth(lat, lon):
            return None
        return lat, lon


def _project_gk(northing: float, easting: float, crs_name: str) -> tuple[float, float] | None:
    if not 0 <= northing <= 10_010_000 or easting <= 0:
        return None
    zone = int(easting // 1_000_000)
    if not 1 <= zone <= 60:
        return None
    residual = easting - zone * 1_000_000
    if not 0 <= residual < 1_000_000:
        return None
    try:
        # always_xy: спочатку схід (повне Y), потім північ (X).
        lon, lat = _gk_transformer(zone, crs_name).transform(easting, northing)
    except Exception:
        return None
    if not _on_earth(lat, lon):
        return None
    central = _norm_lon(6 * zone - 3)
    if _angle_distance(lon, central) > 3.5:
        return None
    return lat, lon


def _signed_dms(deg_raw: str, minute_raw: str, second_raw: str, hemi: str) -> tuple[float, str] | None:
    degrees = _parse_float(deg_raw)
    minutes = _parse_float(minute_raw)
    seconds = _parse_float(second_raw)
    if degrees is None or minutes is None or seconds is None:
        return None
    if degrees < 0 or minutes >= 60 or seconds >= 60:
        return None
    return _magnitude(degrees + minutes / 60 + seconds / 3600, hemi)


def _signed_ddm(deg_raw: str, minute_raw: str, hemi: str) -> tuple[float, str] | None:
    degrees = _parse_float(deg_raw)
    minutes = _parse_float(minute_raw)
    if degrees is None or minutes is None:
        return None
    if degrees < 0 or minutes >= 60:
        return None
    return _magnitude(degrees + minutes / 60, hemi)


def _magnitude(value: float, hemi: str) -> tuple[float, str] | None:
    side = hemi.upper()
    if side in {"N", "S"} and value > 90:
        return None
    if side in {"E", "W"} and value > 180:
        return None
    return _apply_hemi(value, side), side


def _pair_signed(left: tuple[float, str], right: tuple[float, str]) -> tuple[float, float] | None:
    left_value, left_hemi = left
    right_value, right_hemi = right
    lat_sides = {"N", "S"}
    lon_sides = {"E", "W"}
    if left_hemi in lat_sides and right_hemi in lon_sides:
        lat, lon = left_value, right_value
    elif left_hemi in lon_sides and right_hemi in lat_sides:
        lon, lat = left_value, right_value
    else:
        return None
    if not _on_earth(lat, lon):
        return None
    return lat, lon


def _pair_values(raw_left: str, hemi_left: str, raw_right: str, hemi_right: str) -> tuple[float, float] | None:
    left = _parse_float(raw_left)
    right = _parse_float(raw_right)
    if left is None or right is None:
        return None
    left_signed = _magnitude(abs(left), hemi_left)
    right_signed = _magnitude(abs(right), hemi_right)
    if left_signed is None or right_signed is None:
        return None
    return _pair_signed(left_signed, right_signed)


def _compact_mgrs(match: re.Match[str]) -> str | None:
    zone = int(match.group(1))
    if not 1 <= zone <= 60:
        return None
    band = match.group(2).upper()
    square = match.group(3).upper()
    digits = re.sub(r"\s+", "", match.group(4))
    if band not in _SOUTH_BANDS | _NORTH_BANDS | {"N", "S"}:
        return None
    if not 2 <= len(digits) <= 10 or len(digits) % 2 != 0:
        return None
    return f"{zone}{band}{square}{digits}"


def _tighten(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _resolve_overlaps(findings: list[Finding]) -> list[Finding]:
    ranked = sorted(
        findings,
        key=lambda item: (
            -(item.end - item.start),
            _FORMAT_PRIORITY.get(str(item.payload.get("format")), 9),
            item.start,
        ),
    )
    kept: list[Finding] = []
    for finding in ranked:
        if any(finding.start < other.end and other.start < finding.end for other in kept):
            continue
        kept.append(finding)
    kept.sort(key=lambda item: item.start)
    return kept
