"""Frozen backend process boundary; the legacy FastAPI app stays unchanged."""

import argparse
import multiprocessing
import os


if __name__ == "__main__":
    multiprocessing.freeze_support()
    # This EXE is an agent, not a general-purpose Python interpreter. In
    # particular, legacy optional CLI fallbacks must never spawn another server.
    argparse.ArgumentParser(description="YJarvis bundled backend").parse_args()
    import uvicorn
    from jarvis_agent.main import app

    uvicorn.run(
        app,
        host=os.environ.get("JARVIS_AGENT_HOST", "127.0.0.1"),
        port=int(os.environ.get("JARVIS_AGENT_PORT", "8787")),
        loop="asyncio",
        http="h11",
        ws="websockets",
    )
