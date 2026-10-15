"""Convert the official KMA XLSX, without an Excel runtime dependency.

Usage: python -m fire_risk_project.import_kma_regions outputs/kma-regions.xlsx
Source: https://apihub.kma.go.kr/apiList.do?seqApi=10&seqApiSub=286
Attachment: 동네예보지점좌표(위경도)_260701.xlsx
"""
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
import zipfile


def convert(path):
    ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        strings = ["".join(t.itertext()) for t in ET.fromstring(archive.read("xl/sharedStrings.xml")).findall("s:si", ns)]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        regions = []
        for row in sheet.findall(".//s:row", ns)[1:]:
            cells = {}
            for cell in row:
                value = cell.findtext("s:v", default="", namespaces=ns)
                cells[re.sub(r"\d", "", cell.attrib["r"])] = strings[int(value)] if cell.attrib.get("t") == "s" else value
            if cells.get("A") != "kor" or cells.get("E") or not cells.get("F"):
                continue
            regions.append({"id": cells["B"], "province": cells["C"], "district": cells.get("D") or "전체 대표지점",
                            "name": " ".join(filter(None, [cells["C"], cells.get("D")])), "nx": int(cells["F"]), "ny": int(cells["G"])})
    assert len(regions) > 200 and len({r["id"] for r in regions}) == len(regions)
    output = Path(__file__).parent / "data" / "kma-regions.json"
    output.write_text(json.dumps({"source": "https://apihub.kma.go.kr/apiList.do?seqApi=10&seqApiSub=286", "version": "2026-07-01", "regions": regions}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Imported {len(regions)} regions")


if __name__ == "__main__":
    convert(sys.argv[1])
