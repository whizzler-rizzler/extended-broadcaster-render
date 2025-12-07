import uvicorn
from src.api import app
from src.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "src.api:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level="info"
    )
