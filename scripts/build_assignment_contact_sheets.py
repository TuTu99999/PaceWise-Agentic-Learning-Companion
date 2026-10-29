from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs" / "chapter-assignment-png-qa"
DESTINATION = ROOT / "outputs" / "chapter-assignment-contact-sheets"


def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    documents = sorted(path for path in SOURCE.iterdir() if path.is_dir())
    font = ImageFont.load_default(size=18)
    sheet_count = 0
    for start in range(0, len(documents), 2):
        group = documents[start : start + 2]
        rows: list[tuple[str, list[Image.Image]]] = []
        for directory in group:
            pages = [Image.open(path).convert("RGB") for path in sorted(directory.glob("*.png"))]
            rows.append((directory.name, pages))
        page_width = max(image.width for _, pages in rows for image in pages)
        page_height = max(image.height for _, pages in rows for image in pages)
        label_height = 38
        sheet = Image.new("RGB", (page_width * 2, (page_height + label_height) * len(rows)), "white")
        draw = ImageDraw.Draw(sheet)
        for row_index, (label, pages) in enumerate(rows):
            y = row_index * (page_height + label_height)
            draw.rectangle((0, y, sheet.width, y + label_height), fill="#EAF1F8")
            draw.text((12, y + 8), label, fill="black", font=font)
            for column, page in enumerate(pages):
                sheet.paste(page, (column * page_width, y + label_height))
        sheet_count += 1
        sheet.save(DESTINATION / f"sheet-{sheet_count:02d}.png", optimize=True)
        for _, pages in rows:
            for page in pages:
                page.close()
    print(f"Created {sheet_count} contact sheets covering {len(documents) * 2} pages")


if __name__ == "__main__":
    main()
