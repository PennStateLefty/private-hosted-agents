import os
import sys
from pathlib import Path

# Quiet the agent-server telemetry (IMDS + App Insights) during tests.
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ.pop("APPLICATIONINSIGHTS_CONNECTION_STRING", None)

# Make src/ importable (workshop_concierge + adapter packages).
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Make the tests dir importable so `import fakes` works.
_TESTS = Path(__file__).resolve().parent
if str(_TESTS) not in sys.path:
    sys.path.insert(0, str(_TESTS))
