#!/data/data/com.termux/files/usr/bin/bash
# Deploy nkiri/web/static to Cloudflare Pages without wrangler or node.
#
# Cloudflare's direct-upload flow, as wrangler implements it:
#   1. GET  /accounts/{acct}/pages/projects/{proj}/upload-token   -> jwt
#   2. POST /pages/assets/check-missing   {hashes}                -> which to send
#   3. POST /pages/assets/upload          [{key,value,metadata}]  -> base64 bodies
#   4. POST /pages/assets/upsert-hashes   {hashes}
#   5. POST /accounts/{acct}/pages/projects/{proj}/deployments    multipart manifest
#
# The deployment response carries no jwt; that comes from step 1. Files must
# exist server-side before step 5 or the deployment ships empty.
#
# Usage:  CF_TOKEN=... CF_ACCOUNT=... ./scripts/deploy-pages.sh [branch]
set -euo pipefail

: "${CF_TOKEN:?set CF_TOKEN}"
: "${CF_ACCOUNT:?set CF_ACCOUNT}"
PROJECT="${CF_PROJECT:-k-rink}"
BRANCH="${1:-main}"
API="https://api.cloudflare.com/client/v4"
SRC="$(cd "$(dirname "$0")/../nkiri/web/static" && pwd)"

ctype() {
  case "$1" in
    *.html) echo "text/html; charset=utf-8" ;;
    *.js)   echo "application/javascript; charset=utf-8" ;;
    *.css)  echo "text/css; charset=utf-8" ;;
    *.woff) echo "font/woff" ;;
    *.woff2) echo "font/woff2" ;;
    *.svg)  echo "image/svg+xml" ;;
    *.png)  echo "image/png" ;;
    *.json) echo "application/json" ;;
    *)      echo "application/octet-stream" ;;
  esac
}

echo "==> upload token"
JWT=$(curl -sS -H "Authorization: Bearer $CF_TOKEN" \
  "$API/accounts/$CF_ACCOUNT/pages/projects/$PROJECT/upload-token" | jq -r '.result.jwt')
[ -n "$JWT" ] && [ "$JWT" != "null" ] || { echo "no jwt"; exit 1; }

echo "==> hashing $SRC"
cd "$SRC"
FILES=$(find . -type f | sed 's|^\./||' | sort)
HASHES=$(for f in $FILES; do sha256sum "$f" | cut -d' ' -f1; done | jq -R . | jq -s -c .)

echo "==> check-missing"
MISSING=$(curl -sS -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  --data "{\"hashes\":$HASHES}" "$API/pages/assets/check-missing" | jq -c '.result')

echo "==> upload $(echo "$MISSING" | jq 'length') new asset(s)"
PAYLOAD='[]'
for f in $FILES; do
  h=$(sha256sum "$f" | cut -d' ' -f1)
  if echo "$MISSING" | jq -e --arg h "$h" 'index($h)' >/dev/null; then
    b64=$(base64 -w0 "$f")
    PAYLOAD=$(echo "$PAYLOAD" | jq -c \
      --arg k "$h" --arg v "$b64" --arg ct "$(ctype "$f")" \
      '. + [{key:$k, value:$v, metadata:{contentType:$ct}, base64:true}]')
  fi
done
if [ "$(echo "$PAYLOAD" | jq 'length')" -gt 0 ]; then
  curl -sS -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
    --data "$PAYLOAD" "$API/pages/assets/upload" | jq -c '{success, errors:[.errors[]?|{code,message}]}'
fi

echo "==> upsert-hashes"
curl -sS -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
  --data "{\"hashes\":$HASHES}" "$API/pages/assets/upsert-hashes" \
  | jq -c '{success, errors:[.errors[]?|{code,message}]}'

echo "==> manifest"
MANIFEST='{}'
for f in $FILES; do
  h=$(sha256sum "$f" | cut -d' ' -f1)
  MANIFEST=$(echo "$MANIFEST" | jq -c --arg k "/$f" --arg v "$h" '. + {($k):$v}')
done

echo "==> create deployment"
curl -sS -X POST -H "Authorization: Bearer $CF_TOKEN" \
  -F "branch=$BRANCH" \
  -F "manifest=$MANIFEST" \
  "$API/accounts/$CF_ACCOUNT/pages/projects/$PROJECT/deployments" \
  | jq -c '{success, url: .result.url, id: .result.id, errors:[.errors[]?|{code,message}]}'
