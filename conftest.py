import sys
from pathlib import Path

# Make research_agent's packages importable in all test modules
sys.path.insert(0, str(Path(__file__).parent / "research_agent"))
