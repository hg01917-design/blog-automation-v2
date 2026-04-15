"""CDP WebSocket 공통 유틸리티 — dialog 자동처리 포함"""
import asyncio
import json
import random
import re


async def cdp_session(tab_ws: str, fn, timeout: int = 120):
    """WebSocket 연결 후 fn(ws) 실행. dialog 이벤트 자동 dismiss."""
    import websockets

    async with websockets.connect(tab_ws, ping_interval=20, ping_timeout=30) as ws:
        # Page 이벤트 활성화 (dialog 감지용)
        await _send(ws, "Page.enable")

        # dialog 자동처리 백그라운드 태스크
        dialog_task = asyncio.ensure_future(_auto_dismiss_dialogs(ws))
        try:
            result = await asyncio.wait_for(fn(ws), timeout=timeout)
        finally:
            dialog_task.cancel()
            try:
                await dialog_task
            except (asyncio.CancelledError, Exception):
                pass
        return result


async def _auto_dismiss_dialogs(ws):
    """백그라운드에서 dialog 이벤트를 감지하고 자동으로 dismiss."""
    import websockets
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=2)
            data = json.loads(raw)
            if data.get("method") == "Page.javascriptDialogOpening":
                msg = data.get("params", {}).get("message", "")
                print(f"[Dialog 자동처리] '{msg[:60]}' → dismiss", flush=True)
                await _send(ws, "Page.handleJavaScriptDialog", {"accept": False})
        except (asyncio.TimeoutError, asyncio.CancelledError):
            if asyncio.current_task().cancelled():
                break
        except Exception:
            break


async def _send(ws, method: str, params: dict = None, timeout: int = 10):
    """CDP 메시지 전송 후 응답 반환."""
    msg_id = random.randint(10000, 99999)
    await ws.send(json.dumps({"id": msg_id, "method": method, "params": params or {}}))
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            return None
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 3))
            data = json.loads(raw)
            if data.get("method") == "Page.javascriptDialogOpening":
                msg = data.get("params", {}).get("message", "")
                print(f"[Dialog] '{msg[:60]}' → dismiss", flush=True)
                await ws.send(json.dumps({
                    "id": random.randint(10000, 99999),
                    "method": "Page.handleJavaScriptDialog",
                    "params": {"accept": False}
                }))
                continue
            if data.get("id") == msg_id:
                return data.get("result")
        except asyncio.TimeoutError:
            pass


async def cdp_eval(ws, expr: str, timeout: int = 20, await_promise: bool = False):
    """Runtime.evaluate 실행. dialog 인터셉트 포함."""
    result = await _send(ws, "Runtime.evaluate", {
        "expression": expr,
        "returnByValue": True,
        "awaitPromise": await_promise
    }, timeout)
    if result is None:
        return None
    if "exceptionDetails" in result:
        err = result["exceptionDetails"].get("exception", {}).get("description", "?")
        print(f"  JS오류: {err[:120]}", flush=True)
        return None
    return result.get("result", {}).get("value")


async def cdp_navigate(ws, url: str, wait_load: bool = True, timeout: int = 15):
    """CDP Page.navigate로 URL 이동 + dialog 자동처리 + 로드 대기."""
    # Page.enable 먼저 (dialog 이벤트 수신 위해)
    await _send(ws, "Page.enable")

    mid = random.randint(10000, 99999)
    await ws.send(json.dumps({"id": mid, "method": "Page.navigate", "params": {"url": url}}))
    print(f"[navigate] → {url}", flush=True)

    deadline = asyncio.get_event_loop().time() + timeout
    nav_done = False
    load_done = not wait_load

    while not (nav_done and load_done):
        remaining = deadline - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 3))
            data = json.loads(raw)
            method = data.get("method", "")

            # dialog 자동 dismiss
            if method == "Page.javascriptDialogOpening":
                msg = data.get("params", {}).get("message", "")
                print(f"[navigate] Dialog 감지: '{msg[:60]}' → dismiss", flush=True)
                await ws.send(json.dumps({
                    "id": random.randint(10000, 99999),
                    "method": "Page.handleJavaScriptDialog",
                    "params": {"accept": False}
                }))

            if data.get("id") == mid:
                nav_done = True
                print(f"[navigate] 완료", flush=True)

            if method in ("Page.loadEventFired", "Page.frameStoppedLoading"):
                load_done = True
                print(f"[navigate] 로드 완료 ({method})", flush=True)

        except asyncio.TimeoutError:
            pass

    final_url = await cdp_eval(ws, "window.location.href", timeout=8)
    print(f"[navigate] 최종 URL: {final_url}", flush=True)
    return final_url
