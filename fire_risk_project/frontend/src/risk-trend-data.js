const fields = {
  siteId: '\uD604\uC7A5ID', siteName: '\uD604\uC7A5\uBA85', imageId: '\uC870\uAC10\uB3C4ID',
  zoneId: '\uC791\uC5C5\uAD6C\uC5EDID', taskId: '\uC791\uC5C5ID', basis: '\uACC4\uC0B0\uAE30\uC900',
  date: '\uD3C9\uAC00\uC77C\uC2DC', id: '\uD3C9\uAC00ID', score: '\uC704\uD5D8\uC9C0\uC218', grade: '\uC704\uD5D8\uC218\uC900',
};

export const formatRiskIndex = value => value == null || !Number.isFinite(Number(value)) ? '\uBBF8\uC0B0' : `${Number(value).toFixed(2)}\uC810`;

export const zoneRecordKey = record => [record[fields.siteId], record[fields.imageId], record[fields.zoneId]].join('/');

export function groupZoneSeries(records, siteName, selectedZoneKey) {
  const groups = new Map();
  for (const record of records.filter(item => item[fields.siteName] === siteName && zoneRecordKey(item) === selectedZoneKey)) {
    const key = JSON.stringify([record[fields.taskId], ...(record[fields.basis] || [])]);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  }
  return [...groups.entries()].map(([key, items]) => ({ key, records: items }));
}

export function groupLegacySeries(records, siteName) {
  if (!siteName) return [];
  const groups = new Map();
  for (const record of records) {
    if (!record.group?.[0] || !record.group?.[1]) continue;
    const key = JSON.stringify(record.group);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(record);
  }
  return [...groups.entries()].map(([key, items]) => ({ key, records: items }));
}

export function buildTrendPoints(records, isZoneSeries) {
  const sorted = [...records].sort((a, b) => new Date(a[fields.date] || a.date) - new Date(b[fields.date] || b.date) || String(a[fields.id] || a.id).localeCompare(String(b[fields.id] || b.id)));
  return sorted.map((record, index) => {
    const score = isZoneSeries ? record[fields.score] : record.score;
    const previous = index ? (isZoneSeries ? sorted[index - 1][fields.score] : sorted[index - 1].score) : null;
    return {
      id: record[fields.id] || record.id,
      date: record[fields.date] || record.date,
      score: score == null ? null : Number(score),
      grade: isZoneSeries ? record[fields.grade] : record.grade,
      delta: index && score != null && previous != null ? Number(score) - Number(previous) : null,
    };
  });
}
