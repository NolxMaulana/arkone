import httpx
import json
import time
import base64
import asyncio
from typing import List, Optional, Dict
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TokenRequest(BaseModel):
    token: str

class Colors:
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    END = '\033[0m'

class Logger:
    def __init__(self, websocket: Optional[WebSocket] = None):
        self.websocket = websocket

    async def log(self, message: str, color: str = "", end: str = "\n", same_line: bool = False):
        clean_message = message.replace(Colors.CYAN, "").replace(Colors.MAGENTA, "").replace(Colors.BLUE, "").replace(Colors.YELLOW, "").replace(Colors.GREEN, "").replace(Colors.RED, "").replace(Colors.BOLD, "").replace(Colors.END, "")
        if self.websocket:
            await self.websocket.send_json({
                "type": "log", 
                "message": message, 
                "clean": clean_message, 
                "color": color, 
                "same_line": same_line
            })

# --- REFACTORED LOGIC FROM task.py (ASYNC) ---

class KGenEngageBot:
    def __init__(self, token: str, logger: Logger, client: httpx.AsyncClient):
        self.token = token
        self.logger = logger
        self.client = client
        self.CAMPAIGN_IDS = [
            "7585dbbc-0f88-48d8-b22c-7b640a45a79f", # Kickstart Your POGE
            "4221a801-c49c-443c-8106-45d09c89c139", # KDrop Campaign
            "2270e7db-9fc2-457f-9267-515462d2e023", # New Airdrop Campaign
            "7ed14636-0649-4bac-a00c-ddb5572eb0e0"  # New Campaign
        ]
        self.CAMPAIGN_BASE_URL = "https://prod-api-backend.kgen.io/platform-campaign-hub/s2s/airdrop-campaign/user-progress"
        self.LIST_URL = "https://prod-api-backend.kgen.io/platform-campaign-hub/s2s/airdrop-campaign/campaigns?limit=20&offset=0"
        self.DISCONNECT_URL = "https://prod-api-backend.kgen.io/social-auth/disconnect"
        self.MAX_RETRIES = 20
        self.SKIP_TASK_KEYWORDS = ["Selfie", "Complete this K-Drop Campaign", "Complete any one K-Quest"]
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Origin": "https://engage.kgen.io",
            "Referer": "https://engage.kgen.io/",
            "source": "website",
            "request-source": "website",
            "sec-gpc": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        }

    def _get_headers(self, cid=None):
        h = self.headers.copy()
        if cid == "2270e7db-9fc2-457f-9267-515462d2e023":
            h.update({
                "Accept": "application/json",
                "sec-ch-ua": '"Chromium";v="140", "Not=A?Brand";v="24", "Google Chrome";v="140"',
                "sec-ch-ua-mobile": "?0",
                "sec-ch-ua-platform": '"Windows"',
                "sec-fetch-dest": "empty",
                "sec-fetch-mode": "cors",
                "sec-fetch-site": "same-site"
            })
        return h

    async def _fetch_active_campaigns(self):
        h = self._get_headers()
        try:
            r = await self.client.get(self.LIST_URL, headers=h, timeout=10)
            if r.status_code == 200:
                c = r.json().get("campaigns", [])
                return [x for x in c if x.get("campaignStatus") in ["LIVE", "STARTED"]]
            return []
        except: return []

    async def _start_campaign(self, user_id, cid):
        url = f"{self.CAMPAIGN_BASE_URL}/{user_id}/campaigns/{cid}/start"
        h = self._get_headers(cid)
        try:
            r = await self.client.post(url, headers=h, json={}, timeout=10)
            return r.status_code == 200
        except: return False

    async def _fetch_campaign_tasks(self, user_id, cid):
        url = f"{self.CAMPAIGN_BASE_URL}/{user_id}/campaigns/{cid}"
        h = self._get_headers(cid)
        try:
            r = await self.client.get(url, headers=h, timeout=10)
            return r.json() if r.status_code == 200 else None
        except: return None

    async def _validate_task(self, user_id, cid, tid):
        url = f"{self.CAMPAIGN_BASE_URL}/{user_id}/campaigns/{cid}/tasks/{tid}/validate"
        h = self._get_headers(cid)
        try:
            r = await self.client.post(url, headers=h, json={}, timeout=10)
            return r.status_code == 200
        except: return False

    async def _disconnect_social(self, provider):
        h = self._get_headers()
        h["source"] = "app"
        try:
            r = await self.client.request("DELETE", self.DISCONNECT_URL, headers=h, json={"provider": provider}, timeout=10)
            return r.status_code == 200, r.json().get("message", "Success")
        except: return False, "Error"

    async def process_campaign(self, user_id, cid, title):
        await self._start_campaign(user_id, cid)
        data = await self._fetch_campaign_tasks(user_id, cid)
        if not data: return
            
        tasks = data.get("campaignInfo", {}).get("campaignTasks", [])
        progress = data.get("userCampaignProgressInfo", {}).get("progressDetails", [])
        if not tasks: return

        task_status_map = {p.get("taskID"): p.get("userCampaignTaskProgressState") for p in progress}
        to_complete = [t for t in tasks if task_status_map.get(t.get("taskID")) != "VALIDATED"]
        
        prog_text = f"{len(tasks) - len(to_complete)}/{len(tasks)}"
        await self.logger.log(f"   {Colors.CYAN}🔥 {title: <25}{Colors.END} | Progress: {Colors.YELLOW}{prog_text}{Colors.END}")
        
        for task in to_complete:
            t_id, t_title = task.get("taskID"), task.get("title")
            if any(kw.lower() in t_title.lower() for kw in self.SKIP_TASK_KEYWORDS): continue
                
            success = False
            for attempt in range(self.MAX_RETRIES):
                status = f" ({attempt+1}/{self.MAX_RETRIES})" if attempt > 0 else ""
                await self.logger.log(f"      {Colors.YELLOW}⚡ {t_title[:30]}...{status}{Colors.END}", same_line=True)
                if await self._validate_task(user_id, cid, t_id):
                    await self.logger.log(f"      {Colors.GREEN}✅ {t_title[:30]}...      {Colors.END}")
                    success = True; break
                await asyncio.sleep(1.5)
            if not success: await self.logger.log(f"      {Colors.RED}❌ {t_title[:30]}...      {Colors.END}")

# --- REFACTORED LOGIC FROM spin.py (ASYNC) ---

class KGenInfiniteSpin:
    def __init__(self, token: str, logger: Logger, client: httpx.AsyncClient):
        self.token = token
        self.logger = logger
        self.client = client
        self.BASE_URL = "https://prod-api-backend.kgen.io"
        self.SPIN_ENDPOINT = "/rkade/kgen/v2/spin/wheel"
        self.BETS = [5000, 1000, 500, 100]
        self.CURRENCY = "k_point"
        self.GAME_VALUE = "wh"
        self.DELAY_SECONDS = 0.5
        self.MAX_RETRY_CONN = 5
        self.TIMEOUT = 30
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "Origin": "https://rkade.kgen.io",
            "Referer": "https://rkade.kgen.io/",
            "source": "website",
            "request-source": "website",
            "sec-gpc": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        }

    async def _execute_spin(self, bet_amount):
        payload = {
            "game": self.GAME_VALUE,
            "bet": {"amount": bet_amount, "currency": self.CURRENCY}
        }
        retries = 0
        while retries <= self.MAX_RETRY_CONN:
            try:
                r = await self.client.post(self.BASE_URL+self.SPIN_ENDPOINT, headers=self.headers, json=payload, timeout=self.TIMEOUT)
                if not r.text.strip(): raise ValueError("Empty response")
                return r.status_code, r.json()
            except Exception as e:
                retries += 1
                if retries <= self.MAX_RETRY_CONN:
                    await self.logger.log(f"⚠️ Network Glitch. Retrying {retries}...", Colors.YELLOW)
                    await asyncio.sleep(2)
                    continue
                return 0, str(e)

    async def run_loop(self):
        bet_idx = 0
        count = 0
        while bet_idx < len(self.BETS):
            current_bet = self.BETS[bet_idx]
            status, data = await self._execute_spin(current_bet)
            
            if status == 200 and data.get("success"):
                count += 1
                res = data["data"]["visualResult"]["segment"]
                payout = current_bet * res.get("multiplier", 0)
                rew_label = res.get("label") or res.get("name") or f"x{res.get('multiplier')}"
                await self.logger.log(f" {Colors.CYAN}[#{count:03}]{Colors.END} {Colors.GREEN}WIN{Colors.END} | {Colors.BOLD}{rew_label}{Colors.END} | Payout: {payout}")
                await asyncio.sleep(self.DELAY_SECONDS)
            elif status == 400 and data.get("error", {}).get("code") == "INSUFFICIENT_BALANCE":
                bet_idx += 1
                if bet_idx < len(self.BETS):
                    await self.logger.log(f"📉 Switching to {self.BETS[bet_idx]}...", Colors.YELLOW)
                else: break
            else:
                msg = data.get("error", {}).get("message") if isinstance(data, dict) else str(data)
                await self.logger.log(f"❌ Error: {msg}", Colors.RED)
                break

# --- FASTAPI APP ---

def decode_jwt(token):
    try:
        if token.lower().startswith("bearer "): token = token[7:].strip()
        parts = token.split('.')
        if len(parts) != 3: return None
        payload = parts[1]
        payload += '=' * (-len(payload) % 4)
        decoded = base64.b64decode(payload).decode('utf-8')
        return json.loads(decoded)
    except: return None

async def fetch_user_profile(token, client: httpx.AsyncClient):
    headers = {
        "Authorization": f"Bearer {token}",
        "Origin": "https://engage.kgen.io",
        "Referer": "https://engage.kgen.io/",
        "source": "website",
        "request-source": "website",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    }
    url = "https://prod-api-backend.kgen.io/users/me/profile"
    try:
        r = await client.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("google") or data.get("email") or data.get("username")
        else:
            print(f"DEBUG: Profile API failed with status {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"DEBUG: Profile API Exception: {str(e)}")
    return None

async def fetch_wallet_balance(token, user_id, client: httpx.AsyncClient):
    headers = {
        "Authorization": f"Bearer {token}", 
        "source": "website", 
        "request-source": "website",
        "Origin": "https://engage.kgen.io",
        "Referer": "https://engage.kgen.io/"
    }
    rkgen_url = "https://prod-api-backend.kgen.io/wallets/tokens/balance/v2?chains=Aptos&chains=Arbitrum&chains=BSC&chains=Base&chains=Haqq&chains=KlaytnKaia&chains=Kroma&chains=Polygon&chains=Zksync"
    kpoint_url = f"https://prod-api-backend.kgen.io/platform-currency-manager/balances/{user_id}/K_POINT"
    balances = {"kpoint": 0, "rkgen": 0.0}
    try:
        r = await client.get(kpoint_url, headers=headers, timeout=10)
        if r.status_code == 200: balances["kpoint"] = r.json().get("balance", 0)
        r = await client.get(rkgen_url, headers=headers, timeout=10)
        if r.status_code == 200:
            for b in r.json().get("data", {}).get("balances", []):
                if b.get("token") == "RKGEN": balances["rkgen"] = b.get("amount", 0)
    except: pass
    return balances

@app.post("/api/balance")
async def get_balance(req: TokenRequest):
    payload = decode_jwt(req.token)
    if not payload: raise HTTPException(status_code=400, detail="Invalid token")
    user_id = payload.get("username") or payload.get("sub")
    async with httpx.AsyncClient() as client:
        balances = await fetch_wallet_balance(req.token, user_id, client)
        display_name = await fetch_user_profile(req.token, client)
    return {"user_id": user_id, "display_name": display_name or user_id, "balances": balances}

@app.websocket("/ws/tasks")
async def tasks_websocket(websocket: WebSocket):
    await websocket.accept()
    logger = Logger(websocket)
    try:
        data = await websocket.receive_json()
        token = data.get("token")
        payload = decode_jwt(token)
        if not payload: return
        user_id = payload.get("username") or payload.get("sub")
        
        async with httpx.AsyncClient() as client:
            bot = KGenEngageBot(token, logger, client)
            await logger.log(f"👤 UID: {user_id}", Colors.YELLOW)
            
            active_ids = {cid: cid for cid in bot.CAMPAIGN_IDS}
            fetched = await bot._fetch_active_campaigns()
            for f in fetched: active_ids[f.get("campaignID")] = f.get("title", f.get("campaignID"))
            
            for cid, title in active_ids.items():
                await bot.process_campaign(user_id, cid, title)
                
            await logger.log("⏳ Disconnecting Socials...", Colors.BLUE)
            for p in ["STEAM", "DISCORD", "TWITTER", "TELEGRAM"]:
                await bot._disconnect_social(p)
            await logger.log("✨ All tasks complete!", Colors.GREEN)
        
    except WebSocketDisconnect: pass

@app.websocket("/ws/spin")
async def spin_websocket(websocket: WebSocket):
    await websocket.accept()
    logger = Logger(websocket)
    try:
        data = await websocket.receive_json()
        token = data.get("token")
        async with httpx.AsyncClient() as client:
            bot = KGenInfiniteSpin(token, logger, client)
            await logger.log("⏳ Starting Smart Drain Loop...", Colors.BLUE)
            await bot.run_loop()
            await logger.log("🏁 Session Finished.", Colors.BOLD)
    except WebSocketDisconnect: pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
