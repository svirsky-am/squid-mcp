import asyncio
import signal
from src.service import run_service, shutdown_event, _signal_handler

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Graceful shutdown для работы в качестве системной службы (systemd)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)
        
    try:
        asyncio.run(run_service())
    except KeyboardInterrupt:
        pass