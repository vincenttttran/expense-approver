"""Enable ``py -m expense_approver``."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
