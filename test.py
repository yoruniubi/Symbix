import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as client:
        r = await client.post(
            "https://sukiyoru.eu.cc/v1/chat/completions",
            headers={
                "Authorization": "Bearer ***REDACTED-API-KEY***",
                "Content-Type": "application/json",
            },
            json={
                "model": "gemini-3-flash-preview",
                "messages": [{"role": "user", "content": "hi"}],
            },
            timeout=30,
        )
        print("status:", r.status_code)
        print("body:", r.text[:500])

asyncio.run(test())