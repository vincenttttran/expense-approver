"""Stage 4 governance hook: keep tests/** read-only during fixes.

Reads the PreToolUse payload from stdin. If the tool is about to edit or
create a file under a `tests` directory, it blocks the call (exit code 2)
and explains why. This stops the agent from "fixing" a failing test to
match buggy code instead of fixing the code — the test suite is the
source of truth during Stage 4 (Test).

To deliberately change a test (e.g. a spec amendment), disable this hook
for that step or edit the file outside the agent.
"""

import json
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        # If we can't parse input, don't block real work.
        return 0

    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path:
        return 0

    parts = path.replace("\\", "/").split("/")
    if "tests" in parts:
        sys.stderr.write(
            "Blocked by Stage 4 governance: files under tests/** are read-only "
            "during fixes. Fix the code so the existing test passes, or amend the "
            "spec + test deliberately as a separate, explicit step (see CLAUDE.md "
            "'Testing / Stage 4' section).\n"
        )
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
