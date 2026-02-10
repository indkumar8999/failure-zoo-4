from fastapi import FastAPI
import random, time

app = FastAPI(title="downstream")

@app.get("/ok")
async def ok():
    return {"ok": True}

@app.get("/flaky")
async def flaky():
    # 50% ok, otherwise small delay + non-200 signal
    if random.random() < 0.5:
        return {"ok": True}
    time.sleep(0.05)
    return {"ok": False, "code": 500}
