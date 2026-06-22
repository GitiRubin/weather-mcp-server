from netfree_unstrict_ssl import unstrict_ssl
unstrict_ssl()

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from host import ChatHost

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Hold a single long-lived ChatHost for the whole server lifetime."""
    host = ChatHost()
    # Fail fast at startup if the MCP servers can't be reached.
    await host.connect_mcp_clients()
    app.state.host = host
    try:
        yield
    finally:
        await host.cleanup()


app = FastAPI(title="Weather Assistant UI", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    answer: str
    tool_calls: list[dict]


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    host: ChatHost = app.state.host
    result = await host.process_query(request.message)
    return ChatResponse(answer=result.answer, tool_calls=result.tool_calls)


# Serve everything else under static/ (kept after the routes above so they win).
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web:app", host="127.0.0.1", port=8000, reload=False)
