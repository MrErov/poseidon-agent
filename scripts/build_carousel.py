# ruff: noqa: E501 — Spanish copy lines are intentionally long.
"""Generate the Poseidon Agent LinkedIn carousel.

Outputs a 6-page PDF (cover + the 5 Keel Nav phases) and PNG previews in
``docs/carousel/``. Requires Pillow only (already available in the dev env).

Usage:
    python scripts/build_carousel.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1350
MARGIN = 90

BG_TOP = (6, 18, 30)
BG_BOTTOM = (10, 34, 54)
GOLD = (224, 179, 84)
GOLD_DIM = (176, 138, 62)
WHITE = (242, 245, 248)
MUTED = (154, 172, 190)

FONT_DIR = Path("C:/Windows/Fonts")
SERIF = FONT_DIR / "georgiab.ttf"
SERIF_REG = FONT_DIR / "georgia.ttf"
SERIF_ITALIC = FONT_DIR / "georgiai.ttf"
SANS = FONT_DIR / "segoeui.ttf"
SANS_SEMI = FONT_DIR / "seguisb.ttf"
SANS_BOLD = FONT_DIR / "segoeuib.ttf"

OUT_DIR = Path("docs/carousel")
LOGO = Path("docs/assets/logo.png")


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def text_width(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont) -> float:
    box = draw.textbbox((0, 0), text, font=f)
    return box[2] - box[0]


def wrap(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if text_width(draw, candidate, f) <= max_w or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_tracked(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    f: ImageFont.FreeTypeFont,
    fill: tuple[int, ...],
    tracking: int = 4,
) -> None:
    x, y = xy
    for char in text:
        draw.text((x, y), char, font=f, fill=fill)
        x += text_width(draw, char, f) + tracking


def tracked_width(draw: ImageDraw.ImageDraw, text: str, f: ImageFont.FreeTypeFont, tracking: int) -> float:
    return sum(text_width(draw, c, f) for c in text) + tracking * max(0, len(text) - 1)


def background() -> Image.Image:
    img = Image.new("RGB", (W, H), BG_TOP)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        color = tuple(round(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=color)

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for k in range(7):
        amp = 12 + k * 7
        base = H - 40 - k * 26
        points = [
            (x, base + amp * math.sin(x / 190 + k * 0.9))
            for x in range(-20, W + 21, 6)
        ]
        odraw.line(points, fill=(120, 168, 208, 14), width=1)
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img


def header(img: Image.Image, page: int, total: int = 6) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle([(MARGIN, 74), (MARGIN + 12, 86)], fill=GOLD)
    draw_tracked(draw, (MARGIN + 28, 68), "KEEL NAV", font(SANS_SEMI, 20), MUTED, 5)
    label = f"{page:02d} / {total:02d}"
    f = font(SANS, 20)
    draw.text((W - MARGIN - text_width(draw, label, f), 68), label, font=f, fill=MUTED)


def footer(img: Image.Image, label: str) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    draw.line([(MARGIN, H - 92), (W - MARGIN, H - 92)], fill=(255, 255, 255, 26), width=1)
    f = font(SANS, 19)
    draw_tracked(draw, (MARGIN, H - 70), label.upper(), f, MUTED, 3)


def big_number(img: Image.Image, number: str) -> None:
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    f = font(SERIF, 330)
    tw = text_width(draw, number, f)
    draw.text((W - MARGIN - tw, 96), number, font=f, fill=(255, 255, 255, 6))
    img.alpha_composite(overlay)


def fit_headline(draw: ImageDraw.ImageDraw, lines: list[str], max_w: int, start: int) -> tuple[ImageFont.FreeTypeFont, int]:
    size = start
    while size > 40:
        f = font(SERIF, size)
        if max(text_width(draw, line, f) for line in lines) <= max_w:
            return f, size
        size -= 2
    return font(SERIF, size), size


def content_slide(
    page: int,
    number: str,
    kicker: str,
    headline_lines: list[str],
    bullets: list[str],
    key_line: list[str],
    *,
    key_gold: bool = True,
) -> Image.Image:
    img = background().convert("RGBA")
    big_number(img, number)
    header(img, page)
    draw = ImageDraw.Draw(img)

    draw_tracked(draw, (MARGIN, 236), kicker.upper(), font(SANS_BOLD, 24), GOLD, 7)

    head_f, _ = fit_headline(draw, headline_lines, W - 2 * MARGIN, 82)
    y = 288
    for line in headline_lines:
        draw.text((MARGIN, y), line, font=head_f, fill=WHITE)
        y += int(head_f.size * 1.16)

    y += 18
    draw.rectangle([(MARGIN, y), (MARGIN + 84, y + 4)], fill=GOLD)
    y += 54

    body_f = font(SANS, 32)
    bullet_x = MARGIN + 38
    for bullet in bullets:
        draw.ellipse([(MARGIN, y + 14), (MARGIN + 9, y + 23)], fill=GOLD)
        for line in wrap(draw, bullet, body_f, W - MARGIN - bullet_x):
            draw.text((bullet_x, y), line, font=body_f, fill=(214, 224, 234))
            y += 48
        y += 26

    key_f = font(SERIF_ITALIC, 42)
    key_lines: list[str] = []
    for line in key_line:
        key_lines.extend(wrap(draw, line, key_f, W - 2 * MARGIN))
    key_y = max(y + 40, H - 330)
    for line in key_lines:
        draw.text((MARGIN, key_y), line, font=key_f, fill=GOLD if key_gold else WHITE)
        key_y += 56

    footer(img, "Keel Nav  ·  Poseidon Agent")
    return img.convert("RGB")


def cover() -> Image.Image:
    img = background().convert("RGBA")
    draw = ImageDraw.Draw(img)

    if LOGO.exists():
        logo = Image.open(LOGO).convert("RGBA")
        logo.thumbnail((168, 168), Image.LANCZOS)
        img.alpha_composite(logo, (MARGIN, 92))
        text_x = MARGIN + logo.width + 30
    else:
        text_x = MARGIN

    draw_tracked(draw, (text_x, 128), "POSEIDON AGENT", font(SANS_BOLD, 26), WHITE, 3)
    draw.text((text_x, 172), "v4.1.3  ·  Motor de ejecución", font=font(SANS, 21), fill=MUTED)

    head_lines = ["La IA escribe rápido.", "Sin reglas, te", "hipoteca el proyecto."]
    head_f, size = fit_headline(draw, head_lines, W - 2 * MARGIN, 88)
    y = 404
    for idx, line in enumerate(head_lines):
        fill = GOLD if idx == len(head_lines) - 1 else WHITE
        draw.text((MARGIN, y), line, font=head_f, fill=fill)
        y += int(size * 1.14)

    sub = (
        "5 fases para que tus agentes dejen de improvisar "
        "y empiecen a rendir cuentas."
    )
    sy = y + 46
    for line in wrap(draw, sub, font(SANS, 33), W - 2 * MARGIN):
        draw.text((MARGIN, sy), line, font=font(SANS, 33), fill=(196, 208, 220))
        sy += 48

    # Phase rail preview
    rail_y = 900
    usable = W - 2 * MARGIN
    draw.line([(MARGIN, rail_y), (W - MARGIN, rail_y)], fill=(255, 255, 255, 26), width=1)
    for i in range(5):
        x = MARGIN + usable * i / 4
        if i == 0:
            draw.ellipse([x - 6, rail_y - 6, x + 6, rail_y + 6], fill=GOLD)
        else:
            draw.ellipse([x - 5, rail_y - 5, x + 5, rail_y + 5], outline=(255, 255, 255, 80), width=1)
        label = f"{i:02d}"
        f_label = font(SANS, 15)
        draw.text(
            (x - text_width(draw, label, f_label) / 2, rail_y + 18),
            label,
            font=f_label,
            fill=MUTED,
        )

    # Bottom band
    draw.rectangle([(MARGIN, H - 330), (MARGIN + 84, H - 326)], fill=GOLD)
    draw_tracked(draw, (MARGIN, H - 292), "5 FASES · 1 PROTOCOLO · 0 IMPROVISACIÓN", font(SANS_BOLD, 21), GOLD, 3)
    draw.text((MARGIN, H - 232), "Desliza para ver el flujo completo  →", font=font(SANS, 26), fill=MUTED)

    footer(img, "Keel Nav  ·  Poseidon Agent")
    return img.convert("RGB")


def closing_slide() -> Image.Image:
    img = background().convert("RGBA")
    big_number(img, "04")
    header(img, 6)
    draw = ImageDraw.Draw(img)

    draw_tracked(draw, (MARGIN, 236), "FASE 4", font(SANS_BOLD, 24), GOLD, 7)

    head_f = font(SERIF, 78)
    y = 288
    for line in ["Lo construido", "vs. lo prometido."]:
        draw.text((MARGIN, y), line, font=head_f, fill=WHITE)
        y += 92

    y += 10
    draw.rectangle([(MARGIN, y), (MARGIN + 84, y + 4)], fill=GOLD)
    y += 52

    body_f = font(SANS, 32)
    bullets = [
        "Un reporte de drift compara el código con la spec auditada, línea por línea.",
        "Veredicto explícito: no-drift, drifted o drifted-accepted. Sin autoaprobación.",
    ]
    for bullet in bullets:
        draw.ellipse([(MARGIN, y + 14), (MARGIN + 9, y + 23)], fill=GOLD)
        for line in wrap(draw, bullet, body_f, W - MARGIN - (MARGIN + 38)):
            draw.text((MARGIN + 38, y), line, font=body_f, fill=(214, 224, 234))
            y += 48
        y += 24

    quote_f = font(SERIF_ITALIC, 46)
    qy = H - 470
    for line in ["No necesito agentes autónomos.", "Necesito agentes auditables."]:
        draw.text((MARGIN, qy), line, font=quote_f, fill=GOLD)
        qy += 60

    draw.line([(MARGIN, H - 300), (W - MARGIN, H - 300)], fill=(255, 255, 255, 26), width=1)
    draw.text((MARGIN, H - 266), "github.com/MrErov/poseidon-agent", font=font(SANS_SEMI, 28), fill=WHITE)
    draw.text((MARGIN, H - 214), "MIT  ·  213 tests  ·  Windows / Linux / macOS", font=font(SANS, 23), fill=MUTED)

    footer(img, "Keel Nav  ·  Poseidon Agent")
    return img.convert("RGB")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    pages: list[Image.Image] = [cover()]

    pages.append(
        content_slide(
            2,
            "00",
            "Fase 0",
            ["Primero el mapa.", "Después el plan."],
            [
                "El agente mapea el repositorio real: arquitectura, convenciones, deuda técnica y zonas de riesgo.",
                "Cada fase posterior planea contra ese contexto, no contra suposiciones.",
            ],
            ["Contexto primero. Código después."],
        )
    )

    pages.append(
        content_slide(
            3,
            "01",
            "Fase 1",
            ["El contrato antes", "del código."],
            [
                "Cada historia se escribe como spec: criterios de aceptación verificables, contratos de datos y límites explícitos.",
                "Un auditor ciego revisa la spec sin ver el código. Si encuentra ambigüedad, la rechaza.",
            ],
            ["El auditor no ve el código.", "Solo el contrato."],
        )
    )

    pages.append(
        content_slide(
            4,
            "02",
            "Fase 2",
            ["Rojo. Verde.", "Refactor."],
            [
                "Primero, todos los tests que fallan. Después, el código mínimo para ponerlos en verde.",
                "El agente no puede borrar un test para “arreglar” nada. La suite es el contrato.",
            ],
            ["Sin test que falle, no hay código."],
        )
    )

    pages.append(
        content_slide(
            5,
            "03",
            "Fase 3",
            ["Slices verticales,", "no capas a medias."],
            [
                "Cada historia atraviesa las capas reales (DB, API, UI) y termina en algo que puedes observar funcionando.",
                "Hay un gate humano obligatorio antes de darla por terminada.",
            ],
            ["Si no lo puedes ver funcionando,", "no está hecho."],
        )
    )

    pages.append(closing_slide())

    pdf_path = OUT_DIR / "poseidon-agent-carousel.pdf"
    pages[0].save(
        pdf_path,
        "PDF",
        resolution=150.0,
        save_all=True,
        append_images=pages[1:],
    )

    for i, page in enumerate(pages, start=1):
        page.save(OUT_DIR / f"slide-{i:02d}.png", "PNG", optimize=True)

    print(f"PDF: {pdf_path} ({pdf_path.stat().st_size / 1024:.0f} KB)")
    print(f"PNGs: {len(pages)} slides in {OUT_DIR}")


if __name__ == "__main__":
    main()
