# GROUND TRUTH — TEST A: CODE AUDIT

## Target Component: Asynchronous Distributed Job Queue Worker (`job_worker.py`)

### Seeded Defects Inventory (8 Verified Bugs):

1. **BUG-A1 (State Leak / Active Job Desynchronization)**
   - **Location**: `JobQueue.pop()` and `JobQueue.handle_failure()`
   - **Failure Mechanism**: When a job fails, `handle_failure()` decrements `in_progress` counter, but fails to remove `job.id` from `active_job_ids`. Subsequent attempts to re-enqueue or schedule this job fail because `job.id in active_job_ids` remains true indefinitely.
   - **Severity**: HIGH (Permanent task starvation / state leak)
   - **Correction**: In `handle_failure()`, remove `job.id` from `self.active_job_ids.discard(job.id)`.

2. **BUG-A2 (Race Condition / Token Over-Consumption)**
   - **Location**: `AsyncRateLimiter.acquire()`
   - **Failure Mechanism**: The method checks `if self.tokens < 1: await asyncio.sleep(wait_time)`, then subtracts `self.tokens -= 1` without holding a synchronization lock (`asyncio.Lock`). Multiple concurrent coroutines waking up from `sleep` will simultaneously observe positive tokens and subtract, exceeding the rate limit.
   - **Severity**: MEDIUM-HIGH (Rate limit violation under concurrency)
   - **Correction**: Guard state checks and token depletion inside `async with self._lock:`.

3. **BUG-A3 (Resource Leak on Handshake Failure)**
   - **Location**: `ConnectionPool._create_connection()`
   - **Failure Mechanism**: A socket/stream writer `reader, writer = await asyncio.open_connection(...)` is opened. The code then awaits `self._perform_handshake(writer)`. If handshake fails (e.g. auth timeout/error), an exception is raised without calling `writer.close()` and `await writer.wait_closed()`.
   - **Severity**: MEDIUM (TCP socket descriptor leak)
   - **Correction**: Wrap handshake in `try...except` and ensure `writer.close()` on error.

4. **BUG-A4 (Off-by-One / Truncation Drift in Token Bucket)**
   - **Location**: `TokenBucket.refill()`
   - **Failure Mechanism**: `added_tokens = int(elapsed * self.fill_rate)`. If called frequently with small time intervals where `elapsed * self.fill_rate < 1.0`, `int()` truncates to 0, completely discarding elapsed fractional tokens and starving the bucket.
   - **Severity**: MEDIUM (Artificial throttling under high frequency calls)
   - **Correction**: Accumulate floating-point tokens and only truncate or compare against floats: `self.tokens = min(self.capacity, self.tokens + elapsed * self.fill_rate)`.

5. **BUG-A5 (UnboundLocalError in Exception Cleanup)**
   - **Location**: `Worker.execute_task()`
   - **Failure Mechanism**: In `try:` block, `task_meta = await self.fetch_metadata()`. If `fetch_metadata()` raises, execution jumps to `except Exception:` and then `finally:`. In `finally:`, `if task_meta.get("cleanup"):` is evaluated, raising `UnboundLocalError: local variable 'task_meta' referenced before assignment`.
   - **Severity**: HIGH (Worker crash / masked original exception)
   - **Correction**: Initialize `task_meta = None` prior to `try:` block, or check `if "task_meta" in locals() and task_meta:`.

6. **BUG-A6 (Shallow Copy Mutation of Shared Config)**
   - **Location**: `TaskConfig.derive_child()`
   - **Failure Mechanism**: Uses `new_options = self.options.copy()`. `self.options` contains nested dictionaries (e.g. `{"headers": {"X-Trace": "1"}}`). When child task alters headers, it directly mutates the parent task's dictionary across coroutines.
   - **Severity**: MEDIUM (Cross-task data pollution)
   - **Correction**: Use `copy.deepcopy(self.options)`.

7. **BUG-A7 (Deadlock via Inconsistent Lock Acquisition Order)**
   - **Location**: `QueueRouter.transfer_job(src_queue, dst_queue, job_id)`
   - **Failure Mechanism**: Locks are acquired in positional order: `async with src_queue.lock: async with dst_queue.lock:`. If coroutine 1 transfers from Q1 to Q2 and coroutine 2 transfers from Q2 to Q1 simultaneously, an inverted lock deadlock occurs.
   - **Severity**: HIGH (Asynchronous deadlock / event loop hang)
   - **Correction**: Impose a deterministic global lock ordering (e.g. by `id(queue)` or sorted queue names): `first, second = sorted([src_queue, dst_queue], key=lambda q: q.name)`.

8. **BUG-A8 (Delimiter Injection / Tenant Cache Confusion)**
   - **Location**: `CacheKey.generate(tenant_id, resource_name)`
   - **Failure Mechanism**: Key is constructed as `f"{tenant_id}:{resource_name}"` without escaping colons. A malicious tenant "corp:admin" requesting resource "profile" generates key `"corp:admin:profile"`, identical to tenant "corp" requesting resource "admin:profile".
   - **Severity**: HIGH (Multi-tenant security vulnerability / cache collision)
   - **Correction**: Delimit with escaping (e.g., URL encoding or SHA256 hashing of each component separately).
