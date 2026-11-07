#!/usr/bin/env bash
# Moves a pull request opened by this repository's own automation (the spec sync or
# release-please) to an automatic merge, or holds it for a person (docs/DESIGN.md sections 3.1
# and 13). Identical in all seven server SDK repositories.
#
#   bot-pull-request.sh spec-sync <head branch> [passed|failed]
#   bot-pull-request.sh release
#   bot-pull-request.sh catch-up [<head branch>]
#   bot-pull-request.sh report <result of the CI passed job>
#
# spec-sync without passed|failed reads the conclusion of the latest finished Spec sync run on
# main. catch-up starts every workflow that runs release-please (.github/workflows/*.yml using
# googleapis/release-please-action) on main when main's newest commit has no run of it: a merge
# made by auto-merge that GITHUB_TOKEN turned on starts no push workflow. Given a head branch
# whose open pull request has auto-merge on, it first waits up to three minutes for that merge.
#
# A pull request opened with GITHUB_TOKEN gets its pull_request CI run only after a maintainer
# approves it (this repository is public). workflow_dispatch is exempt, so the script starts
# ci.yml on the pull request's branch. GitHub leaves the check runs of a manual run off the pull
# request, so ci.yml's report job (mode report, in that run) sets a commit status "CI passed" on
# the head commit, which the pull request shows and main's required check reads, and then runs
# catch-up for the merge. The script turns on auto-merge (squash), so GitHub merges only once
# the required check passes.
#
# A pull request waits for a person (label needs-alex, one comment, auto-merge off) when:
# - a spec sync failed a check (usually a missing openapi/overlay.json entry), is a draft, or
#   asks for a major version ("!" or a BREAKING CHANGE footer: an API change never does);
# - a release pull request is for a new major version (an SDK design change);
# - it carries commits that did not come from the automation;
# - main has no required status checks, so auto-merge would not wait for CI.
# The script removes its own needs-alex label once the reason is gone. It leaves alone a pull
# request labelled do-not-merge, one a person labelled needs-alex, and one whose auto-merge a
# person turned off.
#
# Needs GH_TOKEN (the workflow token with actions, contents, issues and pull-requests write;
# statuses write for report), GITHUB_REPOSITORY, gh and jq.
set -euo pipefail

usage() {
  echo "usage: bot-pull-request.sh spec-sync <head branch> [passed|failed] | release | catch-up [<head branch>] | report <result>" >&2
  exit 2
}

kind="${1:-}"
repo="${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is not set}"
base="main"
hold_label="needs-alex"
person_hold_label="do-not-merge"
bot_email="41898282+github-actions[bot]@users.noreply.github.com"

# Starts the release workflows on main for a newest commit that has no run of them, after
# waiting (at most three minutes) for the auto-merge of the open pull request from <branch>.
catch_up() {
  local branch="$1" waiting sha
  if [ -n "$branch" ]; then
    for _ in $(seq 1 18); do
      waiting="$(gh pr list --repo "$repo" --base "$base" --head "$branch" --state open \
        --json autoMergeRequest --jq '[.[] | select(.autoMergeRequest != null)] | length')"
      [ "$waiting" -eq 0 ] && break
      sleep 10
    done
  fi
  sha="$(gh api "repos/${repo}/commits/${base}" --jq '.sha')"
  grep -l 'googleapis/release-please-action' .github/workflows/*.yml | while read -r file; do
    workflow="$(basename "$file")"
    runs="$(gh api "repos/${repo}/actions/workflows/${workflow}/runs?head_sha=${sha}&per_page=1" --jq '.total_count')"
    if [ "$runs" -eq 0 ]; then
      gh workflow run "$workflow" --repo "$repo" --ref "$base"
      echo "Started ${workflow} on ${base} (${sha:0:10}): no run of it had started for that commit."
    else
      echo "${workflow} already ran on ${base} (${sha:0:10})."
    fi
  done
}

case "$kind" in
  spec-sync)
    branch="${2:-}"
    checks="${3:-}"
    [ -n "$branch" ] || usage
    if [ -z "$checks" ]; then
      conclusion="$(gh run list --repo "$repo" --workflow spec-sync.yml --branch "$base" --status completed \
        --limit 1 --json conclusion --jq '.[0].conclusion // "success"')"
      checks=failed
      if [ "$conclusion" = success ]; then
        checks=passed
      fi
    fi
    case "$checks" in passed | failed) ;; *) usage ;; esac
    numbers="$(gh pr list --repo "$repo" --base "$base" --head "$branch" --state open \
      --json number --jq '.[].number')"
    ;;
  release)
    checks=passed
    numbers="$(gh pr list --repo "$repo" --base "$base" --state open --label 'autorelease: pending' \
      --json number,headRefName --jq '.[] | select(.headRefName | startswith("release-please--")) | .number')"
    ;;
  catch-up)
    catch_up "${2:-}"
    exit 0
    ;;
  report)
    result="${2:-}"
    sha="${GITHUB_SHA:?GITHUB_SHA is not set}"
    ref="${GITHUB_REF_NAME:?GITHUB_REF_NAME is not set}"
    case "$result" in
      success | failure) ;;
      *)
        echo "The CI passed job ended with '${result}'; no status reported."
        exit 0
        ;;
    esac
    gh api "repos/${repo}/statuses/${sha}" -f state="$result" -f context="CI passed" \
      -f description="ci.yml run ${GITHUB_RUN_ID:-} (workflow_dispatch): ${result}" \
      -f target_url="${GITHUB_SERVER_URL:-https://github.com}/${repo}/actions/runs/${GITHUB_RUN_ID:-}" > /dev/null
    echo "Set the commit status CI passed=${result} on ${sha:0:10} (${ref})."
    if [ "$result" = success ]; then
      case "$ref" in
        chore/spec-sync | release-please--*) catch_up "$ref" ;;
      esac
    fi
    exit 0
    ;;
  *) usage ;;
esac

is_bot() {
  case "$1" in
    github-actions | 'github-actions[bot]' | app/github-actions) return 0 ;;
    *) return 1 ;;
  esac
}

# Turns auto-merge off and, unless the label is there already, labels and comments once.
hold() {
  local number="$1" reason="$2" labelled="$3"
  echo "::warning::Pull request #${number} waits for a person: ${reason}"
  gh pr merge "$number" --repo "$repo" --disable-auto > /dev/null 2>&1 || true
  if [ "$labelled" = true ]; then
    return 0
  fi
  gh label create "$hold_label" --repo "$repo" --color D93F0B --force \
    --description "Automation stopped: a person merges or closes this pull request" > /dev/null
  gh pr edit "$number" --repo "$repo" --add-label "$hold_label" > /dev/null
  gh pr comment "$number" --repo "$repo" --body "$(
    cat << EOF
**Automatic merge is off:** ${reason}.

A person decides: review the pull request, then merge it with **Squash and merge**, or close it. The automation (\`.github/scripts/bot-pull-request.sh\`) checks again on its next run and removes the \`${hold_label}\` label itself once the reason is gone. To keep this pull request from merging in any case, add the \`${person_hold_label}\` label (docs/DESIGN.md section 13).
EOF
  )" > /dev/null
}

handle() {
  local number="$1"
  local pr title body draft head sha author labelled ours events last_auto reason
  pr="$(gh pr view "$number" --repo "$repo" \
    --json title,body,isDraft,headRefName,headRefOid,labels,autoMergeRequest,author)"
  title="$(jq -r '.title' <<< "$pr")"
  body="$(jq -r '.body // ""' <<< "$pr")"
  draft="$(jq -r '.isDraft' <<< "$pr")"
  head="$(jq -r '.headRefName' <<< "$pr")"
  sha="$(jq -r '.headRefOid' <<< "$pr")"
  author="$(jq -r '.author.login' <<< "$pr")"

  if ! is_bot "$author"; then
    echo "#${number} was opened by ${author}, not by this repository's automation; left alone."
    return 0
  fi
  if jq -e --arg l "$person_hold_label" '.labels | any(.name == $l)' <<< "$pr" > /dev/null; then
    echo "#${number} is labelled ${person_hold_label}; left alone."
    return 0
  fi

  # shellcheck disable=SC2016 # GraphQL variables, not shell ones.
  events="$(gh api graphql -F owner="${repo%%/*}" -F name="${repo#*/}" -F number="$number" -f query='
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
          timelineItems(last: 100, itemTypes: [LABELED_EVENT, AUTO_MERGE_ENABLED_EVENT, AUTO_MERGE_DISABLED_EVENT]) {
            nodes {
              __typename
              ... on LabeledEvent { actor { login } label { name } }
              ... on AutoMergeEnabledEvent { actor { login } }
              ... on AutoMergeDisabledEvent { actor { login } reasonCode }
            }
          }
        }
      }
    }' --jq '.data.repository.pullRequest.timelineItems.nodes')"

  # A person who turned auto-merge off keeps it off. Any disable by a person counts, whatever
  # its reasonCode says; one with no actor (GitHub itself) or by the automation does not.
  local disabler
  last_auto="$(jq -c '[.[] | select(.__typename != "LabeledEvent")] | last // {}' <<< "$events")"
  disabler="$(jq -r 'select(.__typename == "AutoMergeDisabledEvent") | .actor.login // ""' <<< "$last_auto")"
  if [ -n "$disabler" ] && ! is_bot "$disabler"; then
    echo "#${number}: ${disabler} turned auto-merge off; left alone."
    return 0
  fi

  labelled=false
  ours=false
  if jq -e --arg l "$hold_label" '.labels | any(.name == $l)' <<< "$pr" > /dev/null; then
    labelled=true
    if is_bot "$(jq -r --arg l "$hold_label" \
      '[.[] | select(.__typename == "LabeledEvent" and .label.name == $l)] | last | .actor.login // ""' \
      <<< "$events")"; then
      ours=true
    else
      echo "#${number}: a person labelled it ${hold_label}; left alone."
      return 0
    fi
  fi

  reason=""
  case "$kind" in
    spec-sync)
      if [ "$checks" != passed ]; then
        reason="the latest spec sync run failed (the Checks section says which check; the fix is usually an openapi/overlay.json entry or the name upstream)"
      elif [ "$draft" = true ]; then
        reason="the spec sync pull request is a draft"
      elif grep -qE '^[a-z]+(\([^)]*\))?!:' <<< "$title" || grep -qE '^BREAKING[ -]CHANGE:' <<< "$body"; then
        reason="it asks for a major version, and an API change never needs one (docs/DESIGN.md section 13)"
      fi
      ;;
    release)
      local version current
      version="$(grep -oE '[0-9]+\.[0-9]+\.[0-9]+' <<< "$title" | tail -n 1 || true)"
      current="$(gh api "repos/${repo}/contents/.release-please-manifest.json?ref=${base}" \
        -H 'Accept: application/vnd.github.raw+json' | jq -r '.["."] // ""')"
      if [ -z "$version" ] || [ -z "$current" ]; then
        reason="the release version could not be read from the title or .release-please-manifest.json"
      elif [ "${version%%.*}" -gt "${current%%.*}" ]; then
        reason="it releases a new major version (${current} to ${version}), which is an SDK design change (docs/DESIGN.md section 13)"
      fi
      ;;
  esac

  if [ -z "$reason" ]; then
    local people
    people="$(gh api "repos/${repo}/pulls/${number}/commits?per_page=100" \
      --jq ".[] | select(.commit.author.email != \"${bot_email}\") | .sha[0:10]")"
    if [ -n "$people" ]; then
      reason="it has commits that did not come from the automation ($(tr '\n' ' ' <<< "$people" | sed 's/ $//'))"
    fi
  fi
  if [ -z "$reason" ]; then
    local required
    required="$(gh api "repos/${repo}/branches/${base}" \
      --jq '(.protection.required_status_checks.contexts // []) | length')"
    if [ "$required" -eq 0 ]; then
      reason="${base} has no required status checks, so auto-merge would not wait for CI"
    fi
  fi

  if [ -n "$reason" ]; then
    hold "$number" "$reason" "$labelled"
    return 0
  fi
  if [ "$ours" = true ]; then
    gh pr edit "$number" --repo "$repo" --remove-label "$hold_label" > /dev/null
  fi

  # CI for the head commit, unless a run is already there that is not waiting for approval.
  local started
  started="$(gh api "repos/${repo}/actions/workflows/ci.yml/runs?head_sha=${sha}&per_page=100" \
    --jq '[.workflow_runs[] | select(.conclusion != "action_required" and .conclusion != "cancelled")] | length')"
  if [ "$started" -eq 0 ]; then
    gh workflow run ci.yml --repo "$repo" --ref "$head"
    echo "#${number}: started CI on ${head} (${sha:0:10})."
  else
    echo "#${number}: CI already runs on ${sha:0:10}."
  fi

  if [ "$(jq -r '.autoMergeRequest != null' <<< "$pr")" = true ]; then
    echo "#${number}: auto-merge is on."
  else
    gh pr merge "$number" --repo "$repo" --auto --squash --match-head-commit "$sha"
    echo "#${number}: auto-merge on (squash) for ${sha:0:10}; GitHub merges once the required checks pass."
  fi
  echo "- #${number} ${title}: CI started and auto-merge on" >> "${GITHUB_STEP_SUMMARY:-/dev/null}"
}

if [ -z "$numbers" ]; then
  echo "No open ${kind} pull request."
  exit 0
fi
for number in $numbers; do
  handle "$number"
done
