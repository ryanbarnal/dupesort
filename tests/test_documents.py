"""Documents: different drawings that share their title-block text are not duplicates."""

import pytest

from dupesort import documents
from dupesort.core.scanner import scan
from dupesort.settings import Settings

TITLE_BLOCK = (
    "ACME ENGINEERING CONSULTANTS LTD 12 Harbour Road Unit 4 Business Park "
    "PROJECT NEW WAREHOUSE AND OFFICE BUILDING FOR NORTHSIDE LOGISTICS "
    "CLIENT NORTHSIDE LOGISTICS GROUP DRAWN BY RB CHECKED BY JD APPROVED BY MK "
    "SCALE AS SHOWN AT A1 DATE NOVEMBER 2026 REVISION C STATUS FOR CONSTRUCTION "
    "ALL DIMENSIONS IN MILLIMETRES DO NOT SCALE FROM THIS DRAWING REPORT ANY "
    "DISCREPANCIES TO THE ENGINEER BEFORE PROCEEDING WITH THE WORK COPYRIGHT RESERVED"
)


def make_pdf(path, lines, comment=b"", pages=1):
    """A drawing-like PDF: the title block as text, the drawing as line work."""
    words = TITLE_BLOCK.split()
    text_ops = "".join(f"BT /F1 7 Tf 420 {150 - 9 * i} Td ({' '.join(words[i * 8:(i + 1) * 8])}) Tj ET\n"
                       for i in range((len(words) + 7) // 8))
    draw = "".join(f"{x1} {y1} m {x2} {y2} l S\n" for x1, y1, x2, y2 in lines)
    content = ("1 w 20 20 m 822 20 l 822 575 l 20 575 l h S\n" + draw + text_ops).encode()
    objs = [b"<</Type/Catalog/Pages 2 0 R>>",
            b"<</Type/Pages/Kids[" + b" ".join(f"{3 + 2 * i} 0 R".encode() for i in range(pages)) +
            f"]/Count {pages}>>".encode()]
    font = 3 + 2 * pages
    for i in range(pages):
        objs.append(f"<</Type/Page/Parent 2 0 R/MediaBox[0 0 842 595]/Contents {4 + 2 * i} 0 R"
                    f"/Resources<</Font<</F1 {font} 0 R>>>>>>".encode())
        objs.append(f"<</Length {len(content)}>>stream\n".encode() + content + b"\nendstream")
    objs.append(b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>")
    out, offsets = bytearray(b"%PDF-1.4\n%" + comment + b"\n"), []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer<</Size {len(objs) + 1}/Root 1 0 R>>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))
    return path


PLAN = [(60, 300, 380, 300), (60, 300, 60, 520), (380, 300, 380, 520), (60, 520, 380, 520),
        (220, 300, 220, 520), (60, 410, 220, 410)]                      # a floor plan
SECTION = [(60, 100, 380, 100), (60, 100, 220, 300), (220, 300, 380, 100),
           (100, 100, 100, 250), (340, 100, 340, 250), (40, 60, 400, 60)]  # a roof section


def groups_for(tmp_path):
    pytest.importorskip("pypdfium2")
    files = scan([tmp_path], "documents")
    return [sorted(f.path.name for f in g.files)
            for g in documents.find_duplicates(files, Settings())]


def test_different_drawings_with_the_same_title_block_are_not_duplicates(tmp_path):
    make_pdf(tmp_path / "A-101 Ground floor plan.pdf", PLAN)
    make_pdf(tmp_path / "A-301 Roof section.pdf", SECTION)
    # Their text really is the same (that's what fooled the text comparison before).
    a, b = (documents.extract_text(tmp_path / n) for n in
            ("A-101 Ground floor plan.pdf", "A-301 Roof section.pdf"))
    assert documents._words(a) == documents._words(b) and len(documents._words(a)) >= 30
    assert groups_for(tmp_path) == []


def test_the_same_drawing_saved_twice_is_still_found(tmp_path):
    make_pdf(tmp_path / "A-101 Ground floor plan.pdf", PLAN)
    make_pdf(tmp_path / "Copy of plan (for client).pdf", PLAN, comment=b"re-saved")  # not byte-identical
    assert groups_for(tmp_path) == [["A-101 Ground floor plan.pdf", "Copy of plan (for client).pdf"]]


def test_a_different_page_count_is_a_different_document(tmp_path):
    make_pdf(tmp_path / "set.pdf", PLAN, pages=2)
    make_pdf(tmp_path / "sheet.pdf", PLAN, pages=1)
    assert groups_for(tmp_path) == []


def test_autocad_files_are_scanned_and_sorted(tmp_path):
    (tmp_path / "A-101.dwg").write_bytes(b"AC1032" + b"\0" * 100)
    (tmp_path / "copy" ).mkdir()
    (tmp_path / "copy" / "A-101 old.dwg").write_bytes(b"AC1032" + b"\0" * 100)
    (tmp_path / "A-102.dwg").write_bytes(b"AC1032" + b"\1" * 100)
    assert groups_for(tmp_path) == [["A-101 old.dwg", "A-101.dwg"]]  # identical copies only
    moves = documents.plan_type_moves(scan([tmp_path], "documents"))
    assert {t.parent.name for _, t in moves} == {"Drawings"}
