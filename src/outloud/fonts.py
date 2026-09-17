"""Fonts: how a code becomes a character, and whether the glyphs travel with the file.

Two facts about every font decide whether text is readable by a machine:
is the program embedded, and is there a way from the codes in the content
stream to Unicode. The mapping comes from /ToUnicode when present, and
otherwise from the encoding: a simple font with a standard encoding or
/Differences can be read through the Adobe Glyph List; a Type0 font with an
Identity CMap and no /ToUnicode cannot be read at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

import pikepdf

try:
    from fontTools import agl as _agl
except Exception:  # noqa: BLE001
    _agl = None

# Standard encodings (code -> character). Latin-1 is a close stand-in for
# StandardEncoding in the ASCII range; the upper ranges differ but a rule
# only needs "is there a mapping", not glyph-perfect text.
_STD_ENCODINGS = {"WinAnsiEncoding": "cp1252", "MacRomanEncoding": "mac_roman", "StandardEncoding": "latin-1",
                  "MacExpertEncoding": "latin-1", "PDFDocEncoding": "latin-1"}

STANDARD_14 = {"Courier", "Courier-Bold", "Courier-Oblique", "Courier-BoldOblique", "Helvetica", "Helvetica-Bold",
               "Helvetica-Oblique", "Helvetica-BoldOblique", "Times-Roman", "Times-Bold", "Times-Italic",
               "Times-BoldItalic", "Symbol", "ZapfDingbats"}


def _dst_text(dst: str) -> str:
    """A bfchar/bfrange destination as text: UTF-16BE, so a ligature code that
    maps to "fi" yields both letters and an astral character keeps its pair."""
    try:
        raw = bytes.fromhex(dst if len(dst) % 2 == 0 else dst[:-1])
        text = raw.decode("utf-16-be", "replace")
        return text or "\ufffd"
    except Exception:  # noqa: BLE001
        return "\ufffd"


def _dst_codepoint(dst: str) -> int:
    return ord(_dst_text(dst)[0])


def parse_tounicode(stream_bytes: bytes, simple_font: bool) -> tuple[dict[int, str], int]:
    """({code: unicode}, code byte width) from a /ToUnicode CMap.

    The width comes from begincodespacerange when it is unambiguous, else
    from the width of the bfchar/bfrange source tokens. A simple font is
    always one byte per code whatever its CMap declares: Word writes CMaps
    for simple fonts that declare both one- and two-byte ranges.
    """
    text = bytes(stream_bytes).decode("latin-1", "replace")
    out: dict[int, str] = {}
    code_widths, token_widths = set(), set()
    for block in re.findall(r"begincodespacerange(.*?)endcodespacerange", text, re.S):
        for lo, hi in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            if lo and len(lo) == len(hi) and len(lo) % 2 == 0:
                code_widths.add(len(lo) // 2)
    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]{2,8})>\s*<([0-9A-Fa-f]{4,})>", block):
            if len(src) % 2:
                continue
            out[int(src, 16)] = _dst_text(dst)
            token_widths.add(len(src) // 2)
    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        for lo, hi, dst in re.findall(r"<([0-9A-Fa-f]{2,8})>\s*<([0-9A-Fa-f]{2,8})>\s*<([0-9A-Fa-f]{4,})>", block):
            if len(lo) % 2 or len(lo) != len(hi):
                continue
            base = _dst_text(dst)
            lo_i, hi_i = int(lo, 16), int(hi, 16)
            if hi_i - lo_i > 65535:
                continue
            head, last = base[:-1], ord(base[-1])
            for off, code in enumerate(range(lo_i, hi_i + 1)):
                out[code] = head + chr(min(last + off, 0x10FFFF))
            token_widths.add(len(lo) // 2)
        # array form: <lo> <hi> [<dst1> <dst2> ...]
        for lo, hi, arr in re.findall(r"<([0-9A-Fa-f]{2,8})>\s*<([0-9A-Fa-f]{2,8})>\s*\[(.*?)\]", block, re.S):
            if len(lo) % 2 or len(lo) != len(hi):
                continue
            dsts = re.findall(r"<([0-9A-Fa-f]{4,})>", arr)
            for off, dst in enumerate(dsts):
                out[int(lo, 16) + off] = _dst_text(dst)
            token_widths.add(len(lo) // 2)
    if simple_font:
        return out, 1
    widths = code_widths or token_widths
    if len(widths) > 1 and token_widths and len(token_widths) == 1:
        widths = token_widths
    return out, (max(widths) if widths else 1)


@dataclass
class FontInfo:
    key: tuple
    resource_names: set = field(default_factory=set)
    subtype: str = "?"
    base_font: str = "?"
    embedded: bool = False
    type3: bool = False
    symbolic: bool = False
    has_tounicode: bool = False
    cmap: dict = field(default_factory=dict)      # code -> text (usually one character; ligatures give two)
    code_width: int = 1
    encoding_map: dict = field(default_factory=dict)  # code -> unicode from /Encoding, simple fonts
    widths: dict = field(default_factory=dict)    # code -> glyph width (text space * 1000)
    default_width: float = 500.0
    ascent: float = 0.9
    descent: float = -0.2
    codes_shown: set = field(default_factory=set)
    unmapped_codes: set = field(default_factory=set)
    pages: set = field(default_factory=set)

    @property
    def can_map(self) -> bool:
        return self.has_tounicode or bool(self.encoding_map) or self.type3 and bool(self.encoding_map)

    def decode(self, raw: bytes) -> str:
        """Bytes of one show-string to text; unmapped codes become U+FFFD and are recorded."""
        out = []
        w = self.code_width
        if w <= 1:
            for b in raw:
                self.codes_shown.add(b)
                if b in self.cmap:
                    out.append(self.cmap[b])
                elif b in self.encoding_map:
                    out.append(chr(self.encoding_map[b]))
                else:
                    self.unmapped_codes.add(b)
                    out.append("�")
            return "".join(out)
        for i in range(0, len(raw) - (w - 1), w):
            code = int.from_bytes(raw[i:i + w], "big")
            self.codes_shown.add(code)
            if code in self.cmap:
                out.append(self.cmap[code])
            else:
                self.unmapped_codes.add(code)
                out.append("�")
        return "".join(out)

    def width_of(self, code: int) -> float:
        return self.widths.get(code, self.default_width)


def _glyph_to_unicode(name: str) -> Optional[int]:
    if _agl is not None:
        try:
            u = _agl.toUnicode(name)
            if u:
                return ord(u[0])
        except Exception:  # noqa: BLE001
            pass
    m = re.match(r"^(?:uni([0-9A-Fa-f]{4})|u([0-9A-Fa-f]{4,6}))$", name)
    if m:
        return int(m.group(1) or m.group(2), 16)
    return None


def _encoding_map(font: pikepdf.Dictionary, symbolic: bool) -> dict[int, int]:
    enc = font.get("/Encoding")
    out: dict[int, int] = {}
    base = None
    diffs = None
    if isinstance(enc, pikepdf.Name):
        base = str(enc)[1:]
    elif isinstance(enc, pikepdf.Dictionary):
        be = enc.get("/BaseEncoding")
        base = str(be)[1:] if isinstance(be, pikepdf.Name) else None
        diffs = enc.get("/Differences")
    if base is None and not symbolic:
        base = "StandardEncoding"
    if base in _STD_ENCODINGS:
        codec = _STD_ENCODINGS[base]
        for code in range(32, 256):
            try:
                ch = bytes([code]).decode(codec)
                if ch and ch.isprintable():
                    out[code] = ord(ch)
            except Exception:  # noqa: BLE001
                continue
    if isinstance(diffs, pikepdf.Array):
        code = 0
        for item in diffs:
            if isinstance(item, pikepdf.Name):
                u = _glyph_to_unicode(str(item)[1:])
                if u is not None:
                    out[code] = u
                code += 1
            else:
                try:
                    code = int(item)
                except Exception:  # noqa: BLE001
                    pass
    return out


def _descriptor(font: pikepdf.Dictionary) -> Optional[pikepdf.Dictionary]:
    fd = font.get("/FontDescriptor")
    if isinstance(fd, pikepdf.Dictionary):
        return fd
    df = font.get("/DescendantFonts")
    if isinstance(df, pikepdf.Array) and len(df):
        d0 = df[0]
        if isinstance(d0, pikepdf.Dictionary):
            fd = d0.get("/FontDescriptor")
            if isinstance(fd, pikepdf.Dictionary):
                return fd
    return None


def _widths(font: pikepdf.Dictionary, subtype: str) -> tuple[dict[int, float], float]:
    out: dict[int, float] = {}
    default = 500.0
    try:
        if subtype == "Type0":
            df = font.get("/DescendantFonts")
            d0 = df[0] if isinstance(df, pikepdf.Array) and len(df) else None
            if isinstance(d0, pikepdf.Dictionary):
                default = float(d0.get("/DW", 1000))
                w = d0.get("/W")
                if isinstance(w, pikepdf.Array):
                    items = list(w)
                    i = 0
                    while i < len(items):
                        first = items[i]
                        if i + 1 < len(items) and isinstance(items[i + 1], pikepdf.Array):
                            for off, val in enumerate(items[i + 1]):
                                out[int(first) + off] = float(val)
                            i += 2
                        elif i + 2 < len(items):
                            lo, hi, val = int(first), int(items[i + 1]), float(items[i + 2])
                            if hi - lo < 65536:
                                for c in range(lo, hi + 1):
                                    out[c] = val
                            i += 3
                        else:
                            break
        else:
            fc = int(font.get("/FirstChar", 0) or 0)
            ws = font.get("/Widths")
            if isinstance(ws, pikepdf.Array):
                for off, val in enumerate(ws):
                    try:
                        out[fc + off] = float(val)
                    except Exception:  # noqa: BLE001
                        continue
                if out:
                    default = 0.0
            fd = font.get("/FontDescriptor")
            if isinstance(fd, pikepdf.Dictionary) and fd.get("/MissingWidth") is not None:
                default = float(fd.get("/MissingWidth"))
    except Exception:  # noqa: BLE001
        pass
    return out, default


def font_info(font: pikepdf.Dictionary, key: tuple) -> FontInfo:
    fi = FontInfo(key)
    sub = font.get("/Subtype")
    fi.subtype = str(sub)[1:] if isinstance(sub, pikepdf.Name) else "?"
    bf = font.get("/BaseFont")
    fi.base_font = str(bf)[1:] if isinstance(bf, pikepdf.Name) else "?"
    fi.type3 = fi.subtype == "Type3"
    fd = _descriptor(font)
    flags = int(fd.get("/Flags", 0) or 0) if fd is not None else 0
    fi.symbolic = bool(flags & 4) and not bool(flags & 32)
    if fd is not None:
        fi.embedded = any(fd.get(k) is not None for k in ("/FontFile", "/FontFile2", "/FontFile3"))
        try:
            fi.ascent = float(fd.get("/Ascent", 900)) / 1000.0 or 0.9
            fi.descent = float(fd.get("/Descent", -200)) / 1000.0 or -0.2
        except Exception:  # noqa: BLE001
            pass
    if fi.type3:
        fi.embedded = True   # glyphs are content streams inside the file
    tu = font.get("/ToUnicode")
    if isinstance(tu, pikepdf.Stream):
        try:
            fi.cmap, fi.code_width = parse_tounicode(tu.read_bytes(), simple_font=fi.subtype != "Type0")
            fi.has_tounicode = bool(fi.cmap)
        except Exception:  # noqa: BLE001
            fi.has_tounicode = False
    if fi.subtype != "Type0":
        fi.code_width = 1
        fi.encoding_map = _encoding_map(font, fi.symbolic)
    else:
        # Identity CMaps give two-byte codes; a named non-Identity CMap may not,
        # but the ToUnicode width already told us and Identity is the common case.
        if fi.code_width == 1 and not fi.has_tounicode:
            fi.code_width = 2
        # Type0 with a non-Identity ordering (e.g. Adobe-Japan1) is readable
        # through the CID system; treat as mappable so it is not a false positive.
        try:
            d0 = font.get("/DescendantFonts")[0]
            csi = d0.get("/CIDSystemInfo")
            ordering = str(csi.get("/Ordering")) if isinstance(csi, pikepdf.Dictionary) else ""
            if ordering and "Identity" not in ordering and not fi.has_tounicode:
                fi.encoding_map = {-1: 0}   # sentinel: mappable via the CID collection
        except Exception:  # noqa: BLE001
            pass
    fi.widths, fi.default_width = _widths(font, fi.subtype)
    return fi


def collect_fonts(doc) -> dict[tuple, FontInfo]:
    """All fonts in page resources (and in the resources of form XObjects they draw)."""
    out: dict[tuple, FontInfo] = {}

    def add(res, page_index: int, depth: int, seen_forms: set):
        if not isinstance(res, pikepdf.Dictionary) or depth > 6:
            return
        fonts = res.get("/Font")
        if isinstance(fonts, pikepdf.Dictionary):
            for name, font in fonts.items():
                if not isinstance(font, pikepdf.Dictionary):
                    continue
                key = font.objgen if font.objgen != (0, 0) else (page_index, name)
                fi = out.get(key)
                if fi is None:
                    fi = font_info(font, key)
                    out[key] = fi
                fi.resource_names.add(name)
                fi.pages.add(page_index)
        xobjs = res.get("/XObject")
        if isinstance(xobjs, pikepdf.Dictionary):
            for _n, xo in xobjs.items():
                if isinstance(xo, pikepdf.Stream) and str(xo.get("/Subtype")) == "/Form":
                    og = xo.objgen
                    if og in seen_forms:
                        continue
                    seen_forms.add(og)
                    add(xo.get("/Resources"), page_index, depth + 1, seen_forms)

    for page in doc.pages:
        add(page.obj.get("/Resources"), page.index, 0, set())
    return out
