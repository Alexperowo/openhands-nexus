import os
import sys
import time
import json
import subprocess
import requests
import re

PORT = 18096
BASE_URL = f"http://127.0.0.1:{PORT}"
OUT_DIR = r"K:\Project\LLM-tests\Heavy-Model-Comparison\head-to-head"

TASKS = [
    {
        "id": 1,
        "name": "architecture_plan",
        "title": "Task 1: Distributed Architecture Plan (CDC & Cache Invalidation)",
        "prompt": """You are a Principal Distributed Systems Architect. Design a production-grade, fault-tolerant, low-latency Change Data Capture (CDC) and Cache Invalidation pipeline.
Requirements:
1. Primary storage: PostgreSQL 16 partitioned across 4 database shards (tenant-based sharding).
2. Read cache: Redis Cluster (key-value read-through / cache-aside) and OpenSearch (full-text search queries).
3. The system handles 20,000 write ops/sec peak and 150,000 read ops/sec peak across all shards.
4. Latency target: cache invalidation / sync lag must be < 500ms p99 from the moment PostgreSQL commits.
5. Reliability constraints: Must handle partial network partitions between PostgreSQL shards and Kafka/Redpanda brokers without dropping events or corrupting cache consistency. Address split-brain, out-of-order events (e.g. update arriving before insert, or older update overwriting newer update), and backpressure under search reindexing.
6. Provide a concrete architecture diagram (text/mermaid), end-to-end component breakdown (Debezium/Kafka/Flink/workers), event schemas with sequence/version tracking, exact cache invalidation strategy (tombstones vs direct update vs versioned lease), and disaster recovery / partition healing protocol."""
    },
    {
        "id": 2,
        "name": "code_audit",
        "title": "Task 2: Code Audit with Seeded Concurrency Bugs",
        "prompt": """Perform a rigorous Senior Security and Concurrency Code Audit of the following Python production backend module for an asynchronous billing and token quota service.
Identify all bugs, vulnerabilities, race conditions, and resource leaks. For each issue found:
1. Identify the exact line or code block.
2. Explain the precise failure scenario / reproduction trigger under high concurrency.
3. Classify severity: Critical / High / Medium / Low.
4. Provide the exact corrected code.

Here is the code:

```python
import asyncio
import time
from typing import Dict, Optional, Any
import asyncpg

class QuotaService:
    def __init__(self, db_pool: asyncpg.Pool):
        self.db_pool = db_pool
        self.in_memory_cache: Dict[str, Any] = {}
        self.lock = asyncio.Lock()
        self.last_sync = time.time()

    async def check_and_deduct_tokens(self, user_id: str, tokens_needed: int) -> bool:
        # Check in-memory fast path
        user_quota = self.in_memory_cache.get(user_id)
        if user_quota is not None:
            if user_quota['tokens_remaining'] >= tokens_needed:
                # Deduct immediately
                user_quota['tokens_remaining'] -= tokens_needed
                # Schedule async sync to DB without blocking caller
                asyncio.create_task(self._sync_quota_db(user_id, user_quota['tokens_remaining']))
                return True
            return False

        # Cold path: load from database
        conn = await self.db_pool.acquire()
        row = await conn.fetchrow('SELECT tokens_remaining FROM quotas WHERE user_id = $1', user_id)
        if not row:
            await self.db_pool.release(conn)
            return False

        remaining = row['tokens_remaining']
        if remaining >= tokens_needed:
            remaining -= tokens_needed
            await conn.execute('UPDATE quotas SET tokens_remaining = $1 WHERE user_id = $2', remaining, user_id)
            await self.db_pool.release(conn)
            self.in_memory_cache[user_id] = {'tokens_remaining': remaining}
            return True

        await self.db_pool.release(conn)
        return False

    async def _sync_quota_db(self, user_id: str, current_tokens: int):
        conn = await self.db_pool.acquire()
        try:
            await conn.execute('UPDATE quotas SET tokens_remaining = $1 WHERE user_id = $2', current_tokens, user_id)
        except Exception as e:
            # Silent logging to avoid crashing
            print(f'Error syncing quota for {user_id}: {e}')
        finally:
            await self.db_pool.release(conn)

    async def reset_daily_quotas(self, accounts: list = []):
        now = time.time()
        # Reset if more than 86400 seconds passed
        if now - self.last_sync > 86400:
            accounts.append('system_admin')
            for acc in accounts:
                self.in_memory_cache[acc] = {'tokens_remaining': 100000}
            self.last_sync = now
```

Be exhaustive. Do not stop at surface-level observations."""
    },
    {
        "id": 3,
        "name": "bad_architecture_review",
        "title": "Task 3: Bad Architecture Review (Microservices Anti-Patterns)",
        "prompt": """You are a Staff Software Architect called in to review the architecture of an e-commerce platform that is failing under load.
The engineering team submitted this design document for their checkout and order processing workflow:
- The system is split into 6 microservices: `CartService`, `OrderService`, `PaymentService`, `InventoryService`, `NotificationService`, and `ShippingService`.
- When a customer clicks 'Place Order', `OrderService` initiates a synchronous HTTP chain:
  `OrderService` -> HTTP POST to `InventoryService` (holds stock reservation in memory)
  -> HTTP POST to `PaymentService` (calls Stripe)
  -> HTTP POST to `ShippingService` (generates label)
  -> HTTP POST to `NotificationService` (sends confirmation email)
- To achieve ACID consistency across services, the team implemented a custom Two-Phase Commit (2PC) protocol over HTTP REST endpoints (`/prepare`, `/commit`, `/rollback`).
- All 6 microservices connect directly to a single shared PostgreSQL database instance (`shared_prod_db`), sharing tables like `orders`, `users`, and `inventory_items` across foreign keys.
- User sessions are stored in-memory inside `CartService` instances, requiring Kubernetes Ingress sticky sessions (cookie-based affinity).
- When a payment fails or times out (Stripe p99 is ~3.5s), `OrderService` triggers HTTP `/rollback` calls to all preceding services.

Perform a thorough architecture critique:
1. Identify and categorize the major architectural anti-patterns and systemic failure modes (e.g. cascading failures, temporal coupling, scalability bottlenecks, blast radius, data integrity risks).
2. Explain specifically what happens when network partitions or node crashes occur during the custom HTTP 2PC.
3. Propose a modern, production-proven target architecture to replace this design. Include patterns like Outbox, Saga (orchestrated or choreographed), event streaming, and database-per-service separation.
4. Detail a realistic, zero-downtime migration roadmap from the current anti-pattern to the target architecture."""
    },
    {
        "id": 4,
        "name": "difficult_debugging",
        "title": "Task 4: Difficult Debugging (Pool Exhaustion & Coroutine Hang)",
        "prompt": """You are a Principal Site Reliability Engineer and Systems Debugger. A critical incident occurred in a high-throughput async Python service (`data-ingestion-worker`).
Analyze the production incident report, stack traces, and code snippet below. Identify the exact root cause, explain the failure sequence step-by-step, and provide the complete fix.

**Incident Symptoms:**
- Under steady load of 3,500 messages/sec, the service runs normally for ~45 minutes.
- Suddenly, p99 response latency spikes from 15ms to 30,000ms (timeout).
- Memory usage climbs linearly until OOM-killer terminates the pods.
- Thread/coroutine dump shows over 12,000 coroutines stuck in `WAITING` status.
- Database connection pool reports 100% exhaustion (50/50 active connections), but database CPU utilization is near 0%.

**Service Code Snippet:**
```python
import asyncio
import logging
from aiohttp import ClientSession, ClientTimeout
import asyncpg

logger = logging.getLogger(__name__)

class IngestionWorker:
    def __init__(self, db_pool: asyncpg.Pool, enrichment_url: str):
        self.db_pool = db_pool
        self.enrichment_url = enrichment_url
        self.session: ClientSession = None
        self.semaphore = asyncio.Semaphore(50) # Limit concurrent external requests

    async def start(self):
        self.session = ClientSession(timeout=ClientTimeout(total=5.0))

    async def process_batch(self, messages: list[dict]):
        tasks = [self.process_single(msg) for msg in messages]
        # Return exceptions to handle individual message failures gracefully
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

    async def process_single(self, msg: dict):
        # Step 1: Acquire DB connection
        async with self.db_pool.acquire() as conn:
            # Step 2: Rate-limit external enrichment call
            await self.semaphore.acquire()
            try:
                # Step 3: Fetch enrichment data from external HTTP service
                async with self.session.post(self.enrichment_url, json=msg) as resp:
                    if resp.status == 200:
                        extra_data = await resp.json()
                    else:
                        raise RuntimeError(f'Enrichment failed with status {resp.status}')
            finally:
                self.semaphore.release()

            # Step 4: Write enriched message to database
            await conn.execute(
                'INSERT INTO processed_events (id, payload, enriched) VALUES ($1, $2, $3)',
                msg['id'], msg['payload'], extra_data
            )
```

**Diagnostic Coroutine Stack Trace Snippet (Top 5 frames):**
```
Task <coroutine process_single> at file worker.py:27
  await self.semaphore.acquire()  <-- 11,950 tasks waiting here
  ...
Task <coroutine process_single> at file worker.py:32
  async with self.session.post(...) <-- 50 tasks waiting here on socket read
```

Analyze:
1. What is the fatal architectural and resource-ordering defect that causes pool exhaustion and lockups?
2. Trace the exact cascade mechanism that triggers the 12,000 stuck coroutines and OOM.
3. Why does `return_exceptions=True` not prevent the memory explosion?
4. What happens if `resp.status != 200` regarding `extra_data` on line 42?
5. Provide the refactored, production-ready `process_single` and batch handling code with proper timeout, resource lifecycle management, bounded queue/backpressure, and error handling."""
    },
    {
        "id": 5,
        "name": "pr_review",
        "title": "Task 5: Final PR Review (Senior Staff Reviewer)",
        "prompt": """You are a Senior Staff Software Engineer performing a thorough Code Review on a Pull Request.
The PR aims to: 'Add batch user export endpoint with CSV streaming and tenant permission checks'.

Review the following git diff carefully. Provide:
1. Executive Summary and Review Decision (Approve, Request Changes, Reject).
2. Blocking Issues (Bugs, Security vulnerabilities, Data leaks, Performance regressions, Breaking changes).
3. Non-blocking suggestions and code style improvements.
4. Missing test cases and edge cases that MUST be covered before merging.

```diff
diff --git a/app/api/v2/users.py b/app/api/v2/users.py
index a1b2c3d..e4f5g6h 100644
--- a/app/api/v2/users.py
+++ b/app/api/v2/users.py
@@ -1,15 +1,24 @@
 from fastapi import APIRouter, Depends, HTTPException, Query
+from fastapi.responses import StreamingResponse
 from sqlalchemy.orm import Session
 from app.db import get_db
 from app.models import User, Tenant
-from app.auth import get_current_user
+from app.auth import get_current_user, get_current_tenant
 import csv
 import io

 router = APIRouter(prefix="/users", tags=["users"])

-@router.get("/")
-def list_users(db: Session = Depends(get_db), current_user = Depends(get_current_user)):
-    return db.query(User).filter(User.tenant_id == current_user.tenant_id).all()
+@router.get("/")
+def list_users(
+    tenant_id: int,
+    db: Session = Depends(get_db), 
+    current_user = Depends(get_current_user)
+):
+    # Allow tenant admin or superuser
+    return db.query(User).filter(User.tenant_id == tenant_id).all()
+
+@router.get("/export")
+def export_users_csv(
+    tenant_id: int,
+    db: Session = Depends(get_db),
+    current_user = Depends(get_current_user)
+):
+    # Query all users for tenant
     users = db.query(User).filter(User.tenant_id == tenant_id).all()
     
     def iter_csv():
         output = io.StringIO()
         writer = csv.writer(output)
         writer.writerow(["ID", "Email", "Full Name", "Password Hash", "Role", "Created At"])
         yield output.getvalue()
         output.seek(0)
         output.truncate(0)
         
         for user in users:
             # Fetch user tenant profile name
             tenant_profile = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
             writer.writerow([user.id, user.email, user.full_name, user.password_hash, user.role, str(user.created_at)])
             yield output.getvalue()
             output.seek(0)
             output.truncate(0)
             
     return StreamingResponse(iter_csv(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=users.csv"})
```

Be extremely thorough and precise."""
    }
]

def kill_and_wait_vram():
    print("Stopping any server and waiting for VRAM cleanup...", flush=True)
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", 
            f"Get-NetTCPConnection -LocalPort {PORT} -ErrorAction SilentlyContinue | ForEach-Object {{ Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }}"], 
            capture_output=True)
    except Exception:
        pass
    subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"], capture_output=True)
    
    for _ in range(25):
        time.sleep(2)
        try:
            out = subprocess.check_output(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"], text=True)
            vram = int(out.strip().split("\n")[0])
            if vram < 1500:
                print(f"VRAM clean: {vram} MiB", flush=True)
                return True
        except Exception:
            pass
    print("VRAM wait finished.", flush=True)
    return False

def wait_ready(proc, timeout=240):
    start = time.time()
    while time.time() - start < timeout:
        if proc.poll() is not None:
            print(f"Subprocess terminated unexpectedly with code {proc.returncode}!", flush=True)
            return False
        try:
            r = requests.get(f"{BASE_URL}/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def run_chat_completion(prompt, max_tokens=1600):
    url = f"{BASE_URL}/v1/chat/completions"
    payload = {
        "messages": [
            {"role": "system", "content": "You are an elite Staff Software Architect and Principal Security Engineer. Provide precise, deep, rigorous technical analysis."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": True
    }
    
    t0 = time.time()
    ttft = None
    chunks = []
    
    with requests.post(url, json=payload, stream=True, timeout=(120, 120)) as resp:
        if resp.status_code != 200:
            raise RuntimeError(f"Chat completion returned {resp.status_code}: {resp.text}")
        
        for line in resp.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("data: "):
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk_json = json.loads(data_str)
                    delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                    content_piece = delta.get("content", "")
                    if content_piece:
                        if ttft is None:
                            ttft = time.time() - t0
                        chunks.append(content_piece)
                except Exception:
                    pass

    total_time = time.time() - t0
    full_text = "".join(chunks)
    
    thinking_text = ""
    answer_text = full_text
    
    think_match = re.search(r"<think>(.*?)</think>", full_text, re.DOTALL)
    if think_match:
        thinking_text = think_match.group(1).strip()
        answer_text = full_text.replace(f"<think>{think_match.group(1)}</think>", "").strip()
    
    est_total_tokens = len(full_text) / 3.6
    est_thinking_tokens = len(thinking_text) / 3.6 if thinking_text else 0
    est_answer_tokens = len(answer_text) / 3.6

    tok_per_sec = (est_total_tokens / (total_time - ttft)) if (total_time and ttft and total_time > ttft) else 0.0

    return {
        "full_text": full_text,
        "thinking_text": thinking_text,
        "answer_text": answer_text,
        "ttft_sec": round(ttft if ttft is not None else total_time, 2),
        "total_time_sec": round(total_time, 2),
        "est_total_tokens": int(round(est_total_tokens)),
        "est_thinking_tokens": int(round(est_thinking_tokens)),
        "est_answer_tokens": int(round(est_answer_tokens)),
        "tok_per_sec": round(tok_per_sec, 2)
    }

def main():
    m_key = "qwen3_next_80b"
    m_name = "Qwen3-Next-80B-Thinking"
    
    print("Starting Qwen3-Next-80B pipeline...", flush=True)
    kill_and_wait_vram()
    
    cmd = [
        r"K:\Project\ik_llama\bin\llama-server.exe",
        "-m", r"K:\Project\Models\Qwen3-Next-80B-A3B-Thinking-UD-Q3_K_XL.gguf",
        "-c", "16384",
        "-ctk", "q8_0",
        "-ctv", "q8_0",
        "-fa", "on",
        "-ngl", "28",
        "-np", "1",
        "-dev", "CUDA0",
        "--jinja",
        "--host", "127.0.0.1",
        "--port", str(PORT),
        "--threads", "8",
        "--threads-batch", "8"
    ]
    
    print(f"Launching: {' '.join(cmd)}", flush=True)
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print("Waiting for /health ready...", flush=True)
    if not wait_ready(proc, timeout=180):
        print("ERROR: Failed to start Qwen3-Next-80B!", flush=True)
        if proc:
            proc.kill()
        return

    print("Server READY! Warming up...", flush=True)
    try:
        requests.post(f"{BASE_URL}/v1/chat/completions", json={
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 1
        }, timeout=30)
    except Exception as e:
        print(f"Warmup notice: {e}", flush=True)
        
    try:
        for task in TASKS:
            t_id = task["id"]
            t_name = task["name"]
            t_title = task["title"]
            out_path = os.path.join(OUT_DIR, f"{m_key}_task_{t_id}.json")
            if os.path.exists(out_path):
                print(f"Task {t_id} already exists, skipping.", flush=True)
                continue
                
            print(f"\n--- Running {t_title} on {m_name} ---", flush=True)
            res = run_chat_completion(task["prompt"], max_tokens=1600)
            res["model_key"] = m_key
            res["model_name"] = m_name
            res["task_id"] = t_id
            res["task_name"] = t_name
            res["task_title"] = t_title
            
            print(f"Done! TTFT: {res['ttft_sec']}s | Total: {res['total_time_sec']}s | Tokens: ~{res['est_total_tokens']} (Think: {res['est_thinking_tokens']}, Ans: {res['est_answer_tokens']}) | Speed: {res['tok_per_sec']} tok/s", flush=True)
            
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(res, f, ensure_ascii=False, indent=2)

        print(f"\nAll tasks for {m_name} completed successfully!", flush=True)
    finally:
        print("Shutting down Qwen3-Next-80B...", flush=True)
        kill_and_wait_vram()

if __name__ == "__main__":
    main()
