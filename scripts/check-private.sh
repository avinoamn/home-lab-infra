#!/usr/bin/env bash
# Fails if any of the given files holds something that must not be in a public repository: a private or
# Tailscale IP address, an email address, a ts.net hostname, a private key or a token.
# Placeholders such as 100.x.y.z, <tailnet>.ts.net or user@example.com pass.
#
# Real values (an SSH user name, the tailnet name) can't be listed here, since this file is public. Put them
# in .private-patterns at the repository root (git-ignored), one extended regex per line, and local runs
# check for them too.
#   bash scripts/check-private.sh <file>...
set -euo pipefail

# The patterns are kept in variables, so this file does not match itself.
ipv4='[0-9]{1,3}'
patterns=(
  "\b10\.$ipv4\.$ipv4\.$ipv4\b"                                     # private range 10/8
  "\b172\.(1[6-9]|2[0-9]|3[01])\.$ipv4\.$ipv4\b"                    # private range 172.16/12
  "\b192\.168\.$ipv4\.$ipv4\b"                                      # private range 192.168/16
  "\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.$ipv4\.$ipv4\b"   # shared range 100.64/10 (Tailscale addresses)
  "\b[a-z0-9-]+\.ts\.net\b"                                         # MagicDNS names and tailnet names
  "-----BEGIN [A-Z ]*PRIVATE KEY-----"
  "\btskey-[a-z]+-[A-Za-z0-9]"                                      # Tailscale auth and API keys
  "\bgh[pousr]_[A-Za-z0-9]{30,}"                                    # GitHub tokens
)
if [ -f .private-patterns ]; then
  while IFS= read -r line; do
    [ -n "$line" ] && [ "${line:0:1}" != "#" ] && patterns+=("$line")
  done < .private-patterns
fi

k3s_defaults='10\.42\.0\.0|10\.43\.0\.0'
email='[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}'
email_ok='noreply@.*|.*@example\.(com|org|net)|.*@users\.noreply\.github\.com|git@github\.com'

[ $# -gt 0 ] || exit 0
found=0
for p in "${patterns[@]}"; do
  # k3s's default pod and service networks are public knowledge, not this lab's addresses.
  if grep -noHIE -- "$p" "$@" | grep -vE ":($k3s_defaults)$"; then found=1; fi
done
if grep -noHIE -- "$email" "$@" | grep -vE -- "^[^:]+:[0-9]+:($email_ok)$"; then found=1; fi

if [ "$found" -ne 0 ]; then
  echo "::error::private values found (above). Replace them with placeholders such as <node>, 100.x.y.z or <tailnet>." >&2
  exit 1
fi
