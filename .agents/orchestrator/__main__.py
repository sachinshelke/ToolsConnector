"""Allow running the orchestrator as a module: python -m agents.orchestrator"""

from .main import main
import sys

sys.exit(main())
