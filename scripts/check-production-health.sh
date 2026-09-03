#!/bin/sh
set -eu

if [ -z "${PUBLIC_BASE_URL:-}" ]; then
  echo "PUBLIC_BASE_URL is required, for example https://raid.example.com" >&2
  exit 1
fi

case "$PUBLIC_BASE_URL" in
  https://*) ;;
  *)
    echo "PUBLIC_BASE_URL must use HTTPS" >&2
    exit 1
    ;;
esac

base_url=${PUBLIC_BASE_URL%/}
host_and_path=${base_url#https://}
case "$host_and_path" in
  */*)
    echo "PUBLIC_BASE_URL must be an origin without a path" >&2
    exit 1
    ;;
esac

headers_file=$(mktemp)
cleanup() {
  rm -f "$headers_file"
}
trap cleanup EXIT HUP INT TERM

curl --fail --silent --show-error "$base_url/api/v1/health/ready" \
  | grep -Eq '"status"[[:space:]]*:[[:space:]]*"ready"'
curl --fail --silent --show-error --head "$base_url/" >"$headers_file"

for required_header in strict-transport-security content-security-policy x-content-type-options; do
  if ! grep -qi "^${required_header}:" "$headers_file"; then
    echo "missing required response header: $required_header" >&2
    exit 1
  fi
done

redirect_result=$(curl --silent --show-error --head --output /dev/null \
  --write-out '%{http_code} %{redirect_url}' "http://$host_and_path/")
case "$redirect_result" in
  "301 $base_url"*|"308 $base_url"*) ;;
  *)
    echo "HTTP endpoint did not redirect to HTTPS: $redirect_result" >&2
    exit 1
    ;;
esac

echo "production health check: ok ($base_url)"
