set -Eeuo pipefail
export PATH="/d/Applications/Scoop/shims:/d/Applications/Scoop/apps/git/current/usr/bin:/d/Applications/Scoop/apps/git/current/bin:$PATH"
work="$1"
tmp="/tmp/rulego-v100-resolve.$$"
mkdir -p "$tmp/resolver" "$tmp/gomodcache" "$tmp/gocache"
git -C /d/Repositories/rulego show v1.0.0:server/go.mod > "$tmp/resolver/go.mod"
git -C /d/Repositories/rulego show v1.0.0:server/go.sum > "$tmp/resolver/go.sum"
export HOME=/c/Users/ying TMPDIR="$tmp" GOMODCACHE="$tmp/gomodcache" GOCACHE="$tmp/gocache"
export CGO_ENABLED=1 GOOS=linux GOARCH=amd64 GOENV=off GOTOOLCHAIN=local GOFLAGS=-mod=readonly GOWORK=off
cd "$tmp/resolver"
{
  echo "go toolchain: $(go env GOVERSION)"
  go mod download all
  go list -m all | LC_ALL=C sort > "$work/module-list.txt"
  go mod graph | LC_ALL=C sort > "$work/module-graph.txt"
  echo "list_sha256: $(sha256sum "$work/module-list.txt" | awk '{print $1}')"
  echo "graph_sha256: $(sha256sum "$work/module-graph.txt" | awk '{print $1}')"
  go list -m -json all > "$work/selected.json"
  echo "replacements: $(python3 -c "import json,sys;mods=[json.loads(l) for l in open(r'$work/selected.json') if l.strip()];print(sum(1 for m in mods if m.get('Replace')))")"
  echo "core: $(python3 -c "import json,sys;mods=[json.loads(l) for l in open(r'$work/selected.json') if l.strip()];print([(m['Path'],m['Version']) for m in mods if m['Path']=='github.com/rulego/rulego'])")"
  echo "go.mod-after: $(sha256sum "$tmp/resolver/go.mod" | awk '{print $1}')"
  echo "go.sum-after: $(sha256sum "$tmp/resolver/go.sum" | awk '{print $1}')"
} > "$work/module-graph-report.txt" 2>&1
rm -rf "$tmp"
