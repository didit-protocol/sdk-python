#!/usr/bin/env bash
# Waits until a package registry serves a released version, and fails the release run loudly
# when it does not (docs/DESIGN.md section 13). Identical in all seven server SDK repositories.
#
#   wait-for-registry.sh <pypi|npm|go|maven|packagist|rubygems|nuget> <package> <version> [minutes]
#
# <package> is the registry's name for it: didit-sdk, @didit-protocol/sdk-node,
# github.com/didit-protocol/sdk-go, me.didit:didit-java, didit-protocol/sdk-php, Didit.
# <version> may carry the tag's "v". Checks every 30 seconds; the default wait is 30 minutes.
set -euo pipefail

registry="${1:?usage: wait-for-registry.sh <registry> <package> <version> [minutes]}"
package="${2:?usage: wait-for-registry.sh <registry> <package> <version> [minutes]}"
version="${3:?usage: wait-for-registry.sh <registry> <package> <version> [minutes]}"
minutes="${4:-30}"
version="${version#v}"

case "$registry" in
  pypi) url="https://pypi.org/pypi/${package}/${version}/json" ;;
  npm) url="https://registry.npmjs.org/${package/\//%2F}/${version}" ;;
  go) url="https://proxy.golang.org/${package}/@v/v${version}.info" ;;
  maven)
    group="${package%%:*}"
    artifact="${package#*:}"
    url="https://repo1.maven.org/maven2/${group//.//}/${artifact}/${version}/${artifact}-${version}.pom"
    ;;
  packagist) url="https://repo.packagist.org/p2/${package}.json" ;;
  rubygems) url="https://rubygems.org/api/v2/rubygems/${package}/versions/${version}.json" ;;
  nuget)
    id="$(tr '[:upper:]' '[:lower:]' <<< "$package")"
    lower="$(tr '[:upper:]' '[:lower:]' <<< "$version")"
    url="https://api.nuget.org/v3-flatcontainer/${id}/${lower}/${id}.nuspec"
    ;;
  *)
    echo "::error::Unknown registry '${registry}'."
    exit 2
    ;;
esac

served() {
  local body
  body="$(curl --fail --silent --show-error --location --max-time 30 "$url" 2> /dev/null)" || return 1
  if [ "$registry" = packagist ]; then
    # One metadata file lists every version; Packagist names them after the tags (v1.2.3).
    jq -e --arg v "$version" \
      '[.packages[]?[]? | .version] | any(. == $v or . == ("v" + $v))' > /dev/null <<< "$body"
  fi
}

deadline=$((SECONDS + minutes * 60))
until served; do
  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "::error::${registry} does not serve ${package} ${version} after ${minutes} minutes (${url}). The release is not published: check the publish job and the registry."
    exit 1
  fi
  sleep 30
done
echo "${registry} serves ${package} ${version}: ${url}"
echo "- ${registry} serves \`${package}\` ${version}: ${url}" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
