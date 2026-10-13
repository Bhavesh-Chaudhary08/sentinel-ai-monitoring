"""Hosted-mode proof: no Redis, no Celery — dashboard + live alerts all in one process."""
import asyncio
import json
import os
import uuid

import httpx
import websockets

ROOT = os.environ.get("PROOF_ROOT", "http://127.0.0.1:8010")
BASE = f"{ROOT}/api/v1"
_ws_scheme = "wss" if ROOT.startswith("https://") else "ws"
WS_URL = f"{_ws_scheme}://{ROOT.split('://', 1)[1]}/api/v1/ws/alerts?token={{tok}}"


async def main() -> None:
    suffix = uuid.uuid4().hex[:8]
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        # 1. register (friend flow)
        r = await c.post("/auth/register", json={
            "email": f"hosted-proof-{suffix}@example.com",
            "full_name": "Hosted Proof",
            "password": "HostedProof1!",
        })
        print("1) register:", r.status_code)
        assert r.status_code == 201, r.text
        user_tok = r.json()["access_token"]
        auth = {"Authorization": f"Bearer {user_tok}"}

        # 2. consent / enroll
        r = await c.post("/auth/consent", json={
            "accepted": True,
            "device_id": f"hosted-proof-device-{suffix}",
            "extension_version": "1.0.0",
        }, headers=auth)
        print("2) consent:", r.status_code, "->", {k: r.json().get(k) for k in ("consented", "enrolled")})
        assert r.status_code == 200, r.text

        # 3. admin login for the WS feed
        r = await c.post("/auth/token", data={"username": "admin@corp.example", "password": "Admin@12345"})
        print("3) admin login:", r.status_code)
        assert r.status_code == 200, r.text
        admin_tok = r.json()["access_token"]

        # 4. connect the dashboard WebSocket (Redis URL points at a dead port)
        frames: list[str] = []

        async def listen() -> None:
            async with websockets.connect(WS_URL.format(tok=admin_tok), open_timeout=10) as ws:
                print("4) websocket: CONNECTED (redis unreachable -> DB polling mode)")
                while True:
                    frames.append(await asyncio.wait_for(ws.recv(), timeout=25))

        listener = asyncio.create_task(listen())
        await asyncio.sleep(1.5)

        # 5. risky capture (contains a real-looking SSN -> should flag + alert)
        r = await c.post("/capture/interactions", json={
            "device_id": f"hosted-proof-device-{suffix}",
            "events": [{
                "client_event_id": uuid.uuid4().hex,
                "occurred_at": "2026-10-13T10:00:00Z",
                "ai_tool": "chatgpt",
                "domain": "chatgpt.com",
                "prompt_text": "Draft an email to HR: my SSN is 123-45-6789, please update my file.",
                "was_blocked": False,
            }],
        }, headers=auth)
        print("5) capture:", r.status_code, r.text[:120])
        assert r.status_code == 200, r.text

        # 6. wait for the alert frame pushed over the websocket
        try:
            await asyncio.wait_for(listener, timeout=20)
        except asyncio.TimeoutError:
            pass
        listener.cancel()

        alert_frames = [f for f in frames if '"alert"' in f]
        pings = [f for f in frames if '"ping"' in f]
        print(f"6) frames received: {len(frames)} (pings={len(pings)}, alerts={len(alert_frames)})")
        assert alert_frames, f"NO ALERT FRAME RECEIVED. frames={frames}"
        payload = json.loads(alert_frames[0])
        print("   ALERT:", payload["severity"], "-", payload["title"])
        print("\nHOSTED-MODE PROOF: PASS — dashboard + live alerts with NO redis, NO celery")


asyncio.run(main())
