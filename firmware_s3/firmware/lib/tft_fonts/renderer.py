try:
    from lib.tft_fonts import ui as _ui_font
    from lib.tft_fonts import data as _data_font
except ImportError:
    try:
        from tft_fonts import ui as _ui_font
        from tft_fonts import data as _data_font
    except ImportError:
        try:
            from . import ui as _ui_font
            from . import data as _data_font
        except ImportError:
            import ui as _ui_font
            import data as _data_font


_FONTS = {
    "ui": _ui_font,
    "data": _data_font,
}


def _rgb565_blend(src, dst, alpha):
    if alpha <= 0:
        return dst
    if alpha >= 15:
        return src
    sr = (src >> 11) & 0x1F
    sg = (src >> 5) & 0x3F
    sb = src & 0x1F
    dr = (dst >> 11) & 0x1F
    dg = (dst >> 5) & 0x3F
    db = dst & 0x1F
    inv = 15 - alpha
    r = ((sr * alpha) + (dr * inv) + 7) // 15
    g = ((sg * alpha) + (dg * inv) + 7) // 15
    b = ((sb * alpha) + (db * inv) + 7) // 15
    return (r << 11) | (g << 5) | b


def _font(style):
    return _FONTS.get(style, _ui_font)


def height(style="ui"):
    return _font(style).HEIGHT


def text_width(text, style="ui", spacing=0):
    font = _font(style)
    total = 0
    text = str(text)
    for ch in text:
        glyph = font.GLYPHS.get(ch)
        if glyph is None:
            glyph = font.GLYPHS.get("?")
        if glyph is not None:
            total += glyph[4] + int(spacing)
    if total and spacing:
        total -= int(spacing)
    return max(0, total)


def bounds(x, y, text, style="ui", spacing=0):
    return (int(x), int(y), text_width(text, style, spacing), height(style))


def draw_text(fb, x, y, text, style="ui", color=0xFFFF, bg=None, spacing=0):
    font = _font(style)
    text = str(text)
    cursor = int(x)
    y = int(y)
    dirty = None
    for ch in text:
        glyph = font.GLYPHS.get(ch)
        if glyph is None:
            glyph = font.GLYPHS.get("?")
        if glyph is None:
            continue
        gw, gh, xoff, yoff, adv, data = glyph
        gx0 = cursor + xoff
        gy0 = y + yoff
        idx = 0
        for gy in range(gh):
            py = gy0 + gy
            if py < 0:
                idx += gw
                continue
            for gx in range(gw):
                px = gx0 + gx
                byte = data[idx >> 1]
                alpha = byte >> 4 if (idx & 1) == 0 else byte & 0x0F
                idx += 1
                if alpha == 0 or px < 0:
                    continue
                if bg is None:
                    try:
                        dst = fb.pixel(px, py)
                    except Exception:
                        continue
                else:
                    dst = bg
                try:
                    fb.pixel(px, py, _rgb565_blend(color, dst, alpha))
                except Exception:
                    continue
        if gw > 0 and gh > 0:
            rect = (gx0, gy0, gw, gh)
            if dirty is None:
                dirty = rect
            else:
                x1 = min(dirty[0], rect[0])
                y1 = min(dirty[1], rect[1])
                x2 = max(dirty[0] + dirty[2], rect[0] + rect[2])
                y2 = max(dirty[1] + dirty[3], rect[1] + rect[3])
                dirty = (x1, y1, x2 - x1, y2 - y1)
        cursor += adv + int(spacing)
    return dirty or (int(x), y, 0, font.HEIGHT)


def draw_centered(fb, width, y, text, style="ui", color=0xFFFF, bg=None, spacing=0):
    x = max(0, (int(width) - text_width(text, style, spacing)) // 2)
    return draw_text(fb, x, y, text, style, color, bg, spacing)
