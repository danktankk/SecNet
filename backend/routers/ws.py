import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services import aggregator

router = APIRouter()


class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            try:
                self.active.remove(ws)
            except ValueError:
                pass


manager = ConnectionManager()


@router.websocket("/ws/feed")
async def feed(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            summary = await aggregator.get_summary()
            await ws.send_json({"type": "summary", "data": summary})
            await asyncio.sleep(15)
    except (WebSocketDisconnect, Exception):
        manager.disconnect(ws)
