"""Agent Service bounded-context facades.

The implementation modules remain available for backwards compatibility, while
new code enters through the six boundaries shown in the architecture panorama:
orchestration, retrieval/evidence, execution, knowledge, governance and
observability.  These facades intentionally do not own persistence; stores stay
behind their existing modules until a separately versioned migration is ready.
"""

from .context import RequestContext

__all__ = ["RequestContext"]
