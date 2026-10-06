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
    # Codes (simple fonts) or CIDs (Type0 with an Identity CMap) that resolve to a real
    # glyph in the embedded program; None when the program could not be read, is not
    # embedded, or the CMap is not Identity, in which case only code 0 is judged.
    glyphs: Optional[set] = None
    identity_cmap: bool = True
    notdef_codes: set = field(default_factory=set)

    def is_notdef(self, code: int) -> bool:
        """Does this code reach the .notdef glyph? ISO 14289-1 7.21.8 forbids showing it in any render mode."""
        if self.code_width >= 2:
            if code == 0 and self.identity_cmap:
                return True
            return self.glyphs is not None and self.identity_cmap and code not in self.glyphs
        return self.glyphs is not None and code not in self.glyphs

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


# ── which codes have a glyph ─────────────────────────────────────────────

def _std_names(base: Optional[str]) -> dict[int, str]:
    """code -> glyph name for the predefined simple-font encodings."""
    out: dict[int, str] = {}
    try:
        if base == "WinAnsiEncoding":
            from fontTools.agl import UV2AGL  # noqa: PLC0415
            for code in range(32, 256):
                try:
                    ch = bytes([code]).decode("cp1252")
                except Exception:  # noqa: BLE001
                    out[code] = "bullet"          # Annex D: unused WinAnsi codes above 127 show a bullet
                    continue
                if code == 0xA0:
                    out[code] = "space"
                elif code == 0xAD:
                    out[code] = "hyphen"
                else:
                    # Annex D: in WinAnsiEncoding every unused code above octal 40 shows a bullet,
                    # so 0x7F and the undefined 0x80–0x9F codes have a glyph, not .notdef.
                    out[code] = UV2AGL.get(ord(ch)) or "bullet"
        elif base == "MacRomanEncoding":
            from fontTools.encodings.MacRoman import MacRoman  # noqa: PLC0415
            for code, name in enumerate(MacRoman):
                if name and name != ".notdef":
                    out[code] = name
        elif base in ("StandardEncoding", "PDFDocEncoding"):
            from fontTools.encodings.StandardEncoding import StandardEncoding  # noqa: PLC0415
            for code, name in enumerate(StandardEncoding):
                if name and name != ".notdef":
                    out[code] = name
    except Exception:  # noqa: BLE001
        return {}
    return out


def _encoding_names(font: pikepdf.Dictionary, symbolic: bool, builtin: Optional[dict[int, str]]) -> dict[int, str]:
    """code -> glyph name after the font's /Encoding: base table (or the program's built-in one), then /Differences."""
    enc = font.get("/Encoding")
    base = None
    diffs = None
    if isinstance(enc, pikepdf.Name):
        base = str(enc)[1:]
    elif isinstance(enc, pikepdf.Dictionary):
        be = enc.get("/BaseEncoding")
        base = str(be)[1:] if isinstance(be, pikepdf.Name) else None
        diffs = enc.get("/Differences")
    if base is not None:
        names = _std_names(base)
    elif builtin:
        names = dict(builtin)
    elif not symbolic:
        names = _std_names("StandardEncoding")
    else:
        names = {}
    if isinstance(diffs, pikepdf.Array):
        code = 0
        for item in diffs:
            if isinstance(item, pikepdf.Name):
                names[code] = str(item)[1:]
                code += 1
            else:
                try:
                    code = int(item)
                except Exception:  # noqa: BLE001
                    pass
    return names


def _type1_program(data: bytes) -> tuple[set, dict[int, str]]:
    """(glyph names, built-in encoding) of a Type 1 font program (FontFile), PFA or PFB-less raw."""
    from fontTools.misc import eexec  # noqa: PLC0415

    head, _, tail = data.partition(b"eexec")
    builtin: dict[int, str] = {}
    if b"StandardEncoding" in head:
        builtin = _std_names("StandardEncoding")
    for m in re.finditer(rb"dup\s+(\d+)\s*/(\S+)\s+put", head):
        builtin[int(m.group(1))] = m.group(2).decode("latin-1")
    tail = tail.lstrip(b"\r\n\t ")
    if re.fullmatch(rb"[0-9A-Fa-f\s]+", tail[:64] or b"x"):
        try:
            tail = bytes.fromhex(re.sub(rb"\s+", b"", tail).decode("ascii"))
        except Exception:  # noqa: BLE001
            pass
    plain, _r = eexec.decrypt(tail, 55665)
    names = {m.group(1).decode("latin-1") for m in re.finditer(rb"/([^\s/{}\[\]()<>]+)\s+\d+\s+(?:RD|-\|)[ ]", plain)}
    return names, builtin


def _cff_program(data: bytes) -> tuple[Optional[set], dict[int, str], bool]:
    """(glyph names or CIDs, built-in encoding, cid_keyed) of a bare CFF program (FontFile3)."""
    import io  # noqa: PLC0415
    from fontTools.cffLib import CFFFontSet  # noqa: PLC0415

    cff = CFFFontSet()
    cff.decompile(io.BytesIO(data), None)
    top = cff.topDictIndex[0]
    charset = list(top.charset or [])
    if hasattr(top, "ROS"):
        cids = set()
        for i, n in enumerate(charset):
            if n.startswith("cid") and n[3:].isdigit():
                cids.add(int(n[3:]))
            elif i:
                cids.add(i)
        return cids, {}, True
    names = {n for n in charset if n != ".notdef"}
    builtin: dict[int, str] = {}
    try:
        enc = top.Encoding
        if isinstance(enc, (list, tuple)):
            builtin = {c: n for c, n in enumerate(enc) if n and n != ".notdef"}
        elif isinstance(enc, str):
            builtin = _std_names(enc if enc.endswith("Encoding") else enc + "Encoding")
    except Exception:  # noqa: BLE001
        pass
    return names, builtin, False


def _truetype_codes(data: bytes, names: dict[int, str], symbolic: bool) -> Optional[set]:
    """Codes of a simple TrueType font that reach a glyph, following ISO 32000-1 9.6.6.4."""
    import io  # noqa: PLC0415
    from fontTools.ttLib import TTFont  # noqa: PLC0415

    tt = TTFont(io.BytesIO(data), lazy=True)
    n_glyphs = tt["maxp"].numGlyphs
    cmap = tt["cmap"] if "cmap" in tt else None
    if cmap is None:
        return {c for c in range(256) if c < n_glyphs}     # no cmap: the code is the glyph index
    sub = {(t.platformID, t.platEncID): t.cmap for t in cmap.tables}
    ms = sub.get((3, 1)); mac = sub.get((1, 0)); sym = sub.get((3, 0))
    post = None
    try:
        post = set(tt.getGlyphOrder())
    except Exception:  # noqa: BLE001
        pass
    out = set()
    for code in range(256):
        name = names.get(code)
        hit = False
        if symbolic or not name:
            if sym and any(k in sym for k in (code, 0xF000 + code, 0xF100 + code, 0xF200 + code)):
                hit = True
            elif mac and code in mac:
                hit = True
        if not hit and name:
            u = _glyph_to_unicode(name)
            if ms and u is not None and u in ms:
                hit = True
            elif mac:
                try:
                    mc = chr(u).encode("mac_roman")[0] if u is not None else None
                    hit = mc is not None and mc in mac
                except Exception:  # noqa: BLE001
                    hit = False
            if not hit and post and name in post:
                hit = True
        if not hit and not name and not symbolic and ms is None and mac is None and sym is None:
            hit = code < n_glyphs
        if hit:
            out.add(code)
    return out


def _cid_glyphs(d0: pikepdf.Dictionary, fd: pikepdf.Dictionary) -> Optional[set]:
    """CIDs of a CIDFont that reach a glyph in its embedded program, or None when unknown."""
    import io  # noqa: PLC0415

    sub = str(d0.get("/Subtype") or "")
    ff2, ff3 = fd.get("/FontFile2"), fd.get("/FontFile3")
    if sub == "/CIDFontType0" and isinstance(ff3, pikepdf.Stream):
        data = ff3.read_bytes()
        if data[:4] == b"OTTO":
            from fontTools.ttLib import TTFont  # noqa: PLC0415
            tt = TTFont(io.BytesIO(data), lazy=True)
            cff = tt["CFF "].cff
            top = cff.topDictIndex[0]
            charset = list(top.charset or [])
            if hasattr(top, "ROS"):
                return {int(n[3:]) for n in charset if n.startswith("cid") and n[3:].isdigit()}
            return set(range(1, len(charset)))
        glyphs, _b, cid_keyed = _cff_program(data)
        return glyphs if cid_keyed else set(range(1, len(glyphs) + 1))
    if sub == "/CIDFontType2" and isinstance(ff2, pikepdf.Stream):
        from fontTools.ttLib import TTFont  # noqa: PLC0415
        tt = TTFont(io.BytesIO(ff2.read_bytes()), lazy=True)
        n = tt["maxp"].numGlyphs
        c2g = d0.get("/CIDToGIDMap")
        if isinstance(c2g, pikepdf.Stream):
            m = c2g.read_bytes()
            return {cid for cid in range(len(m) // 2) if 0 < int.from_bytes(m[2 * cid:2 * cid + 2], "big") < n}
        return set(range(1, n))
    return None


def glyph_coverage(font: pikepdf.Dictionary, fi: "FontInfo") -> None:
    """Fill fi.glyphs (and fi.identity_cmap) from the embedded program; leave None when it cannot be known."""
    try:
        if fi.type3:
            procs = font.get("/CharProcs")
            names = _encoding_names(font, True, {})
            if isinstance(procs, pikepdf.Dictionary):
                have = {k[1:] for k in procs.keys()}
                fi.glyphs = {c for c, n in names.items() if n in have}
            return
        fd = _descriptor(font)
        if fd is None or not fi.embedded:
            return
        if fi.subtype == "Type0":
            enc = font.get("/Encoding")
            fi.identity_cmap = isinstance(enc, pikepdf.Name) and str(enc) in ("/Identity-H", "/Identity-V")
            if not fi.identity_cmap:
                return
            df = font.get("/DescendantFonts")
            d0 = df[0] if isinstance(df, pikepdf.Array) and len(df) else None
            if isinstance(d0, pikepdf.Dictionary):
                fi.glyphs = _cid_glyphs(d0, fd)
            return
        ff1, ff2, ff3 = fd.get("/FontFile"), fd.get("/FontFile2"), fd.get("/FontFile3")
        if isinstance(ff2, pikepdf.Stream):
            names = _encoding_names(font, fi.symbolic, None)
            fi.glyphs = _truetype_codes(ff2.read_bytes(), names, fi.symbolic)
            return
        if isinstance(ff1, pikepdf.Stream):
            glyph_names, builtin = _type1_program(ff1.read_bytes())
        elif isinstance(ff3, pikepdf.Stream):
            data = ff3.read_bytes()
            if data[:4] == b"OTTO":
                from fontTools.ttLib import TTFont  # noqa: PLC0415
                import io  # noqa: PLC0415
                tt = TTFont(io.BytesIO(data), lazy=True)
                glyph_names = set(tt.getGlyphOrder()) - {".notdef"}
                builtin = {}
            else:
                g, builtin, cid_keyed = _cff_program(data)
                if cid_keyed:
                    return
                glyph_names = g or set()
        else:
            return
        if not glyph_names:
            return
        names = _encoding_names(font, fi.symbolic, builtin)
        fi.glyphs = {c for c, n in names.items() if n in glyph_names}
    except Exception:  # noqa: BLE001
        fi.glyphs = None


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
    glyph_coverage(font, fi)
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
