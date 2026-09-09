"""Stage 5 governance hook: production deploys require named authorization.

Reads the PreToolUse payload from stdin. If the agent is about to run a Bash
command that looks like a release / deploy / publish action, the call is
BLOCKED (exit code 2) unless a named human authorization is present in the
environment variable ``DEPLOY_APPROVED_BY``.

This makes the playbook's Stage 5 rule mechanical: "the agent can prepare a
release but cannot pass production gates." A human clears the gate by setting,
for the authorized command only:

    DEPLOY_APPROVED_BY="Vincent Tran" <deploy command>

The gate is intentionally conservative — it matches on deploy verbs, not on a
full command parse. Preparing a release (editing files, running tests, building
locally) is never blocked; only the act of shipping is.
"""

import json
import os
import re
import sys

# Commands that constitute "shipping". These match actual invocations, not the
# mere appearance of a word — so a commit message or branch name that mentions
# "deploy"/"release"/"publish" is NOT blocked, only a command that ships is.
# Case-insensitive.
DEPLOY_PATTERNS = (
    r"gh\s+release\s+create",            # cut a GitHub release
    r"\btwine\s+upload\b",               # publish to PyPI
    r"\bdocker\s+push\b",                # push an image
    r"\bkubectl\s+apply\b",              # apply to a cluster
    r"\bterraform\s+apply\b",            # apply infra changes
    r"\bgit\s+push\b[^\r\n|;&]*--tags",  # push release tags
    r"\bgit\s+push\b[^\r\n|;&]*\b(prod|production)\b",  # push to a prod branch/remote
    r"\b(?:npm|yarn|pnpm)\s+run\s+(?:deploy|release|publish)\b",  # package-script ship
    r"\bmake\s+(?:deploy|release|publish)\b",                      # make target
    # A deploy script invoked as a command. Requires a real invocation shape so
    # prose like "... and deploy gate" in a commit message is NOT matched:
    r"\bdeploy\.(?:sh|ps1|bat|py|cmd)\b",                     # deploy.sh anywhere
    r"(?:^|[|;&]\s*)deploy(?:\s|$)",                          # `deploy` at cmd start / after ; | &
    r"(?:^|[\s|;&(])(?:\./|bash\s+|sh\s+)deploy(?:\.\w+)?(?:\s|$)",  # ./deploy, bash deploy
)


def looks_like_deploy(command: str) -> bool:
    return any(re.search(p, command, re.IGNORECASE) for p in DEPLOY_PATTERNS)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # If we can't parse input, don't block real work.
        return 0

    if payload.get("tool_name") not in (None, "Bash"):
        return 0

    command = (payload.get("tool_input") or {}).get("command") or ""
    if not command or not looks_like_deploy(command):
        return 0

    approver = os.environ.get("DEPLOY_APPROVED_BY", "").strip()
    if approver:
        # Named human authorization present — allow, and leave a trail.
        sys.stderr.write(
            f"Deploy gate: authorized by {approver!r}. Proceeding.\n"
        )
        return 0

    sys.stderr.write(
        "Blocked by Stage 5 deploy gate: this looks like a release/deploy/publish "
        "action, which the agent cannot perform on its own. A named human must "
        "authorize it by setting DEPLOY_APPROVED_BY for the command, e.g.:\n"
        '    DEPLOY_APPROVED_BY="Your Name" <command>\n'
        "See REVIEW.md and the playbook Stage 5 (Deploy).\n"
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
