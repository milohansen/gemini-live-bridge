from context import get_context

# This file is kept for backwards compatibility, but the core logic has been
# moved to context.py. New code should import from there directly.

async def fetch_context_via_http():
    """Fetches context using the centralized get_context function."""
    return await get_context()
