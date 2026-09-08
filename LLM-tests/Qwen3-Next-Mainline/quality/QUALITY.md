# Quality Benchmark Evaluation: Qwen3-Next-80B on Official llama.cpp b10816

## 1. Summary Scorecard

| Test | Objective Score | Finish Reason | Turn Latency | TG Speed | MTP Drafts Accepted | Verdict |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **TEST A: Code Audit** | **8 / 8 BUGS FOUND** (100%) | `stop` | **236.4s** | 17.38 tok/s | 1,725 tokens | **PASS (FLAWLESS)** |
| **TEST B: Debugging** | **CONTRADICTION DETECTED** | `stop` | **197.9s** | 16.86 tok/s | 1,312 tokens | **PASS (FLAWLESS)** |

---

## 2. Test A: Objective Deep Code Audit (8 Seeded Defects)

### Results against `quality/GROUND-TRUTH-A.md`:
1. **BUG-A1 (State Leak)**: `JobQueue.handle_failure` fails to discard from `active_job_ids` -> **FOUND**.
2. **BUG-A2 (Race Condition)**: `AsyncRateLimiter.acquire` checks and updates tokens across sleep without lock -> **FOUND**.
3. **BUG-A3 (Resource Leak)**: `ConnectionPool` fails to close stream writer on handshake error -> **FOUND**.
4. **BUG-A4 (Logic / Truncation)**: `TokenBucket.refill` truncates fractional tokens with `int()` -> **FOUND**.
5. **BUG-A5 (UnboundLocalError)**: `Worker.execute_task` accesses `task_meta` in `finally:` if assignment fails -> **FOUND**.
6. **BUG-A6 (Data Mutation)**: `TaskConfig.derive_child` uses shallow `.copy()`, mutating parent options -> **FOUND**.
7. **BUG-A7 (Deadlock)**: `QueueRouter.transfer_job` acquires dual locks in asymmetric order -> **FOUND**.
8. **BUG-A8 (Security / Delimiter Injection)**: `CacheKey.generate` concatenates tenant and resource with unescaped colon -> **FOUND**.

- **False Positives**: 0.
- **Verified Code Fixes**: Provided for all 8 defects.

---

## 3. Test B: Forensic Debugging & Contradictory Evidence

### Results against `quality/GROUND-TRUTH-B.md`:
1. **Refuted False Heap Premise**: Model explicitly highlighted that heap memory was only at 412 MiB (40% of 1024 MiB max), proving the crash was NOT a Java heap leak.
2. **Identified True Root Cause (Native / Off-Heap OOM)**: Demonstrated that the Linux kernel cgroup OOM killer terminated the container because native memory working set reached 2047 MiB.
3. **Pinpointed Netty Direct Buffer Allocation**: Identified that `Unpooled.directBuffer(capacity)` in `TransactionBuffer` allocates off-heap memory outside the JVM heap.
4. **Log / Code Discrepancy**: Noted the discrepancy in the stack trace and advised checking log aggregation routing and adding `-XX:NativeMemoryTracking=summary`.
