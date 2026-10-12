"""Refresh the read-only UI reference bundle from existing CSVs; no DB writes."""
import csv
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
def rows(name):
    with (root / 'data' / name).open(encoding='utf-8-sig', newline='') as source:
        return list(csv.DictReader(source))

bundle = {
    'standards': rows('04_법령_KOSHA기준DB.csv'),
    'accidents': [row for row in rows('03_사고데이터.csv') if row['검수상태'] == '검수완료'],
}
(root / 'frontend/src/reference-data.json').write_text(
    json.dumps(bundle, ensure_ascii=False, indent=2), encoding='utf-8'
)
print('Reference bundle refreshed. Rebuild the frontend to publish updated references.')
