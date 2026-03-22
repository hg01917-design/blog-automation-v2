"""goodisak 전용 에이전트 — it_agent 래퍼"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from agents import it_agent as _base
except ImportError:
    import it_agent as _base

BLOG_ID = _base.BLOG_ID
PERSONA_RULE = _base.PERSONA_RULE
run = _base.run
_parse_raw = _base._parse_raw
