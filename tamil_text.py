"""
tamil_text.py
-------------
ReportLab draws each Unicode character as an isolated glyph with no OpenType
shaping engine (no GSUB/GPOS), so complex scripts like Tamil come out visually
wrong: vowel signs land in the wrong position, and consonant+vowel-sign
ligatures (e.g. the short "u"/"uu" matras) fall back to the wrong shape.

This module shapes Tamil (and any mixed Tamil/Latin/digit) text correctly
using HarfBuzz, rasterizes it with FreeType, and exposes a ReportLab Flowable
(`TamilText`) that draws the result as a crisp raster image, with word-wrap
computed against the real shaped width so it fits table cells / page width
exactly like a normal Paragraph would.

Both `uharfbuzz` and `freetype-py` ship self-contained wheels (statically
bundled HarfBuzz / FreeType binaries) — no system packages (pango/cairo/etc.)
are required, so this works on Render's plain Python build.
"""
import unicodedata
import numpy as np
import uharfbuzz as hb
import freetype
from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable

_HB_FONT_CACHE = {}
_FT_FACE_CACHE = {}


def _get_hb_font(font_path):
    cached = _HB_FONT_CACHE.get(font_path)
    if cached is None:
        blob = hb.Blob.from_file_path(font_path)
        face = hb.Face(blob)
        font = hb.Font(face)
        font.scale = (face.upem, face.upem)
        cached = (font, face.upem)
        _HB_FONT_CACHE[font_path] = cached
    return cached


def _get_ft_face(font_path):
    face = _FT_FACE_CACHE.get(font_path)
    if face is None:
        face = freetype.Face(font_path)
        _FT_FACE_CACHE[font_path] = face
    return face


def _shape(text, font_path):
    hbfont, upem = _get_hb_font(font_path)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf)
    return buf.glyph_infos, buf.glyph_positions, upem


def measure_width_pt(text, font_path, font_size_pt):
    """Width the shaped text will occupy, in PDF points."""
    if not text:
        return 0.0
    infos, positions, upem = _shape(text, font_path)
    total = sum(p.x_advance for p in positions)
    return total * (font_size_pt / upem)


def rasterize_line(text, font_path, font_size_pt, dpi=200):
    """Shape + rasterize a single line of text.
    Returns (PIL.Image RGB, width_pt, height_pt) or None for blank text.
    """
    if not text or not text.strip():
        return None

    scale = dpi / 72.0
    font_size_px = font_size_pt * scale
    infos, positions, upem = _shape(text, font_path)
    if not infos:
        return None

    ft_face = _get_ft_face(font_path)
    ft_face.set_char_size(int(font_size_px * 64))
    px_scale = font_size_px / upem

    pen_x = 0.0
    glyph_data = []
    min_top = 0.0
    max_bottom = 0.0
    for info, pos in zip(infos, positions):
        ft_face.load_glyph(info.codepoint, freetype.FT_LOAD_RENDER | freetype.FT_LOAD_NO_HINTING)
        g = ft_face.glyph
        bw, bh = g.bitmap.width, g.bitmap.rows
        # Copy the buffer NOW: FreeType reuses the same internal buffer on
        # every load_glyph call, so a stored reference would go stale.
        buf_bytes = bytes(g.bitmap.buffer)
        left = g.bitmap_left
        top = g.bitmap_top
        x_off = pos.x_offset * px_scale
        y_off = pos.y_offset * px_scale
        draw_x = pen_x + x_off + left
        draw_y = -(y_off + top)
        glyph_data.append((buf_bytes, bw, bh, draw_x, draw_y))
        min_top = min(min_top, draw_y)
        max_bottom = max(max_bottom, draw_y + bh)
        pen_x += pos.x_advance * px_scale

    width_px = max(1, int(round(pen_x)))
    height_px = max(1, int(round(max_bottom - min_top)))

    canvas = np.full((height_px, width_px), 255, dtype=np.uint8)
    for buf_bytes, bw, bh, draw_x, draw_y in glyph_data:
        if bw == 0 or bh == 0:
            continue
        arr = np.frombuffer(buf_bytes, dtype=np.uint8).reshape(bh, bw)
        ink = 255 - arr
        ox = int(round(draw_x))
        oy = int(round(draw_y - min_top))
        x0, y0 = max(ox, 0), max(oy, 0)
        x1, y1 = min(ox + bw, width_px), min(oy + bh, height_px)
        if x0 >= x1 or y0 >= y1:
            continue
        src = ink[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
        dst = canvas[y0:y1, x0:x1]
        canvas[y0:y1, x0:x1] = np.minimum(dst, src)

    img = Image.fromarray(canvas, mode="L").convert("RGB")
    return img, width_px / scale, height_px / scale


def _split_graphemes(word):
    """Split into Tamil akshara-ish units: each base character plus any
    combining marks that follow it (vowel signs, virama) stay attached, so a
    forced mid-word break never separates a consonant from its vowel sign."""
    tokens = []
    current = ""
    for ch in word:
        if current and unicodedata.category(ch) in ("Mn", "Mc"):
            current += ch
        else:
            if current:
                tokens.append(current)
            current = ch
    if current:
        tokens.append(current)
    return tokens


def _pack_word(word, font_path, font_size_pt, max_width_pt):
    """If `word` (no spaces) is wider than max_width_pt on its own, break it
    at akshara boundaries into pieces that each fit."""
    if measure_width_pt(word, font_path, font_size_pt) <= max_width_pt:
        return [word]
    tokens = _split_graphemes(word)
    pieces = []
    cur = ""
    for t in tokens:
        cand = cur + t
        if not cur or measure_width_pt(cand, font_path, font_size_pt) <= max_width_pt:
            cur = cand
        else:
            pieces.append(cur)
            cur = t
    if cur:
        pieces.append(cur)
    return pieces or [word]


def wrap_words(text, font_path, font_size_pt, max_width_pt):
    """Greedy word-wrap using real shaped widths (space-separated, like Tamil
    and English prose both use). Falls back to akshara-level breaking for a
    single word wider than the available width (e.g. long compound weekday
    names like செவ்வாய்க்கிழமை in a narrow table column)."""
    if not text:
        return [""]
    if max_width_pt <= 0:
        return [text]

    flat_tokens = []  # (piece, breakable_before)
    for w in text.split(" "):
        pieces = _pack_word(w, font_path, font_size_pt, max_width_pt)
        for i, piece in enumerate(pieces):
            flat_tokens.append((piece, i == 0))

    lines = []
    current = ""
    for piece, breakable in flat_tokens:
        if not current:
            current = piece
            continue
        candidate = f"{current} {piece}" if breakable else current + piece
        if measure_width_pt(candidate, font_path, font_size_pt) <= max_width_pt:
            current = candidate
        else:
            lines.append(current)
            current = piece
    lines.append(current)
    return lines or [""]


class TamilText(Flowable):
    """A ReportLab Flowable that draws correctly-shaped Tamil/mixed text as a
    crisp raster image, with word-wrap against the real available width —
    drop-in replacement for Paragraph() wherever Tamil script is involved.

    `text` may contain literal '<br/>' to force a line break (same convention
    the old Paragraph-based code used).
    """

    def __init__(self, text, font_path, font_size_pt, leading_pt=None,
                 align="left", space_after=0, dpi=200):
        Flowable.__init__(self)
        self.raw_text = text or ""
        self.font_path = font_path
        self.font_size_pt = font_size_pt
        self.leading_pt = leading_pt or font_size_pt * 1.35
        self.align = align
        self.space_after = space_after
        self.dpi = dpi
        self._lines = [""]
        self._width = 0
        self._height = self.leading_pt + self.space_after

    def wrap(self, availWidth, availHeight):
        forced_lines = self.raw_text.split("<br/>")
        all_lines = []
        for fl in forced_lines:
            all_lines.extend(wrap_words(fl, self.font_path, self.font_size_pt, availWidth))
        self._lines = all_lines or [""]
        self._width = availWidth
        self._height = self.leading_pt * len(self._lines) + self.space_after
        return self._width, self._height

    def draw(self):
        c = self.canv
        y = self._height - self.space_after
        for line in self._lines:
            y -= self.leading_pt
            if line.strip():
                result = rasterize_line(line, self.font_path, self.font_size_pt, dpi=self.dpi)
                if result:
                    img, w_pt, h_pt = result
                    if self.align == "right":
                        x = self._width - w_pt
                    elif self.align == "center":
                        x = (self._width - w_pt) / 2.0
                    else:
                        x = 0
                    c.drawImage(ImageReader(img), x, y, width=w_pt, height=h_pt)
