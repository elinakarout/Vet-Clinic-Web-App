#!/usr/bin/env bash
# Phase 8's two non-type-checkable guards. See PHASE_8.md § Tests.
#
# There is no test runner in this frontend, so these are bundled with the
# rolldown that ships inside vite and run under node. Both drive the REAL
# modules — a copy of the logic would encode the same assumption as the code and
# agree with any bug in it.
set -euo pipefail
cd "$(dirname "$0")/.."
OUT="${TMPDIR:-/tmp}/vetclinic-chat-checks"
mkdir -p "$OUT"

echo "== SSE framing (api/client.ts:apiStream) =="
./node_modules/.bin/rolldown scripts/stream-harness.ts -o "$OUT/stream.mjs" \
  -f esm -p node --transform.define 'import.meta.env.VITE_API_URL:"http://x"' >/dev/null
node "$OUT/stream.mjs"

echo
echo "== Rendering, under a browser zone that is NOT the clinic's =="
cat > "$OUT/rolldown.config.mjs" <<CONF
export default {
  input: '$PWD/scripts/render-harness.tsx',
  external: [/^react\$/, /^react\//, /^react-dom/, /^@tanstack/, /^react-router/],
  transform: { define: {
    'import.meta.env.VITE_CLINIC_TIMEZONE': '"Asia/Beirut"',
    'import.meta.env.VITE_API_URL': '"http://localhost:8000"',
  } },
  output: { file: '$PWD/.render-harness.mjs', format: 'esm' },
  platform: 'node',
};
CONF
./node_modules/.bin/rolldown -c "$OUT/rolldown.config.mjs" >/dev/null
trap 'rm -f "$PWD/.render-harness.mjs"' EXIT
TZ=America/Los_Angeles node .render-harness.mjs
