"""Wanderer CAD : longueurs tapées et écrites, y compris en unités impériales (pieds ' et pouces ", fractions).

Saisie acceptée (comme AutoCAD, Rhino, SketchUp) :
    126.5        dans l'unité affichée de la scène
    10'          pieds ; 6"  pouces ; 10'6"  10' 6"  10'-6"  10'6
    10' 6 1/2"   10'6-1/2"   10'6+1/2"   6 1/2"   6-1/2"   1/2"   3/4   (fractions)
    -10'6"       signe devant
Écriture des cotes en architectural : 10' - 6 1/2"  (le tiret entre pieds et pouces, comme le veut l'usage).
Ce module ne dépend pas de Blender (testable seul)."""

import math
import re

FOOT_M = 0.3048
INCH_M = 0.0254

_NUM = r"(?:\d+(?:\.\d*)?|\.\d+)"
_FRAC = r"(?:\d+\s*/\s*\d+)"
# pouces : entier ou décimal, éventuellement suivi d'une fraction (6 1/2, 6-1/2, 6+1/2), ou une fraction seule
_INCH = rf"(?:(?P<iw>{_NUM})(?:\s*[ +\-]\s*(?P<if>{_FRAC}))?|(?P<io>{_FRAC}))"
_RE_FTIN = re.compile(rf"^(?P<ft>{_NUM})\s*'\s*(?:[\-+]?\s*{_INCH}\s*(?P<iq>\")?)?$")
_RE_IN = re.compile(rf"^{_INCH}\s*(?P<iq>\")?$")


def _norm(text):
    s = (text or "").strip()
    for a, b in (("′", "'"), ("″", '"'), ("’", "'"), ("”", '"'), ("“", '"'),
                 ("''", '"'), ("´", "'")):
        s = s.replace(a, b)
    s = s.replace(",", ".")
    return s


def _frac(t):
    a, b = t.replace(" ", "").split("/")
    b = float(b)
    if b == 0.0:
        raise ZeroDivisionError
    return float(a) / b


def _inches(m):
    if m.group("io"):
        return _frac(m.group("io"))
    if m.group("iw") is None:
        return None
    v = float(m.group("iw"))
    if m.group("if"):
        v += _frac(m.group("if"))
    return v


def _num_or_frac(t):
    t = t.strip()
    if not t:
        raise ValueError(t)
    return _frac(t) if "/" in t else float(t)


def parse_length(text, unit_f=1.0, m_per_unit=1.0, imperial=False):
    """Longueur tapée -> unités Blender (None si le texte n'est pas une longueur complète).
    unit_f : unités Blender par unité affichée ; m_per_unit : mètres par unité affichée.
    imperial : scène en pieds / pouces, où 10+6+1/2 se lit 10' 6 1/2" (tout au pavé numérique, #14)."""
    s = _norm(text)
    if s in ("", "-", ".", "-.", "+"):
        return None
    sign = 1.0
    if s[0] in "-+":
        sign = -1.0 if s[0] == "-" else 1.0
        s = s[1:].strip()
    if not s:
        return None
    try:
        return sign * float(s) * unit_f            # cas courant : un nombre
    except ValueError:
        pass
    bu_per_m = unit_f / (m_per_unit or 1.0)
    if imperial and "+" in s and "'" not in s and '"' not in s:
        # pieds + pouces (+ fraction de pouce) : 10+6+1/2 = 10' 6 1/2", 10+6 = 10' 6", 10+1/2 = 10' 1/2"
        parts = s.split("+")
        if not 2 <= len(parts) <= 3 or "/" in parts[0]:
            return None
        try:
            ft = float(parts[0].strip())
            inch = sum(_num_or_frac(p) for p in parts[1:])
        except (ValueError, ZeroDivisionError):
            return None
        return sign * (ft * FOOT_M + inch * INCH_M) * bu_per_m
    try:
        m = _RE_FTIN.match(s)
        if m:
            ft = float(m.group("ft"))
            inch = _inches(m) or 0.0
            return sign * (ft * FOOT_M + inch * INCH_M) * bu_per_m
        m = _RE_IN.match(s)
        if m:
            v = _inches(m)
            if v is None:
                return None
            if m.group("iq"):
                return sign * v * INCH_M * bu_per_m          # pouces explicites (")
            return sign * v * unit_f                         # fraction sans marque : dans l'unité affichée
    except (ValueError, ZeroDivisionError):
        return None
    return None


def accepts_char(ch, typed):
    """Le caractère ch peut-il prolonger la saisie `typed` d'une longueur ? (chiffres, point, signe, ' " / + espace)"""
    if not ch or len(ch) != 1:
        return False
    t = typed
    last = t.rstrip()[-1:] if t.strip() else ""
    if ch.isdigit():
        return not t.endswith('"')
    if ch in ".,":
        tail = re.split(r"[\s'\"/+\-]", t)[-1]
        return "." not in tail and not t.endswith('"')
    inch_part = t.split("'")[-1]
    if ch == "+" and t and "'" not in t and '"' not in t and "-" not in t.lstrip("-"):
        # 10+6+1/2 (pieds + pouces + fraction, au pavé numérique) : deux + au plus, avant toute fraction
        return last.isdigit() and t.lstrip("-+").count("+") < 2 and "/" not in t
    if ch == "-" or ch == "+":
        if t == "":
            return True                              # signe
        if last == "'":
            return True                              # 10'-6"
        # 6-1/2 : entre les pouces entiers et la fraction, une seule fois
        return (last.isdigit() and _has_digit(inch_part) and "/" not in inch_part
                and not any(c in inch_part.lstrip("-+") for c in "-+ "))
    if ch == "/":
        return bool(last) and last.isdigit() and "/" not in re.split(r"[\s'+\-]", t)[-1]
    if ch == "'":
        return bool(last) and last.isdigit() and "'" not in t and "/" not in t and '"' not in t
    if ch == '"':
        return bool(last) and last.isdigit() and '"' not in t
    if ch == " ":
        # un espace ne fait partie de la saisie qu'après des pieds (10' 6 1/2") ou avant une fraction (6 1/2") ;
        # sinon Espace garde son rôle (valider)
        return bool(t) and not t.endswith((" ", '"')) and ("'" in t)
    return False


def _has_digit(t):
    return any(c.isdigit() for c in t)


def typing_add(typed, ch):
    """Saisie après la touche ch (la virgule devient un point), ou None si le caractère est refusé."""
    if ch == ",":
        ch = "."
    if ch == "-" and typed == "":
        return "-"
    if not accepts_char(ch, typed):
        return None
    return typed + ch


def is_imperial(system, length_unit):
    return system == 'IMPERIAL' and length_unit in ('FEET', 'INCHES', 'ADAPTIVE', 'MILES', 'THOU')


def fraction_text(v, denom=16):
    """Pouces avec fraction : 6.5 -> '6 1/2', 0.25 -> '1/4', 7.0 -> '7'. Arrondi au 1/denom le plus proche."""
    denom = max(1, int(denom))
    n = int(round(abs(v) * denom))
    whole, rest = divmod(n, denom)
    g = math.gcd(rest, denom) if rest else 1
    parts = []
    if whole or not rest:
        parts.append(str(whole))
    if rest:
        parts.append(f"{rest // g}/{denom // g}")
    return ("-" if v < 0 and n else "") + " ".join(parts)


def format_imperial(metres, unit='FEET', denom=16):
    """Longueur en architectural : 10' - 6 1/2"  (unit='FEET' ou 'ADAPTIVE') ; 126 1/2"  (unit='INCHES')."""
    inches = metres / INCH_M
    neg = inches < 0
    inches = abs(inches)
    denom = max(1, int(denom))
    n = int(round(inches * denom))          # arrondi une seule fois : 11 63/64" ne devient pas 0' - 12"
    if unit == 'INCHES':
        return ("-" if neg and n else "") + fraction_text(n / denom, denom) + '"'
    ft, rest = divmod(n, 12 * denom)
    txt = f"{ft}' - {fraction_text(rest / denom, denom)}\""
    return ("-" if neg and n else "") + txt


def denom_for_precision(decimals):
    """Précision des cotes (décimales) -> dénominateur des fractions, comme AutoCAD : 0 -> 1", 4 -> 1/16", 6 -> 1/64"."""
    return 2 ** max(0, min(6, int(decimals)))
