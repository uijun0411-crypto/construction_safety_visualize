const allowedValues = new Set(['예', '아니오', '확인불가']);

export function buildWatcherAnswers(extras, allowedIds, exceptionRequired = true) {
  const allowed = new Set(allowedIds || []);
  return Object.fromEntries(Object.entries(extras || {}).filter(([id, value]) =>
    allowed.has(id) && allowedValues.has(value) && (id !== 'W004' || exceptionRequired)
  ));
}
