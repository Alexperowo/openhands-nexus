# ARCHITECTURAL RUBRIC — TEST C: DISTRIBUTED EVENT SOURCING & FINANCIAL LEDGER

## 12 Mandatory Architecture Requirements (1 point each, Total 12 points):

1. **REQ-1: Event Ordering & Partitioning**
   - Must specify deterministic partition keys (e.g., `account_id` or `ledger_id`) to ensure strict per-entity sequential ordering while scaling horizontally across partitions/shards.

2. **REQ-2: End-to-End Idempotency**
   - Must specify idempotency keys at the API layer combined with unique database constraints (or deductive event deduplication) to prevent double debits/credits on retries.

3. **REQ-3: Dual-Write Elimination & Transactional Outbox**
   - Must avoid dual-writing to database and message broker. Must use Transactional Outbox pattern or Change Data Capture (CDC / Debezium) to guarantee atomic persistence.

4. **REQ-4: Concurrency & Optimistic Concurrency Control (OCC)**
   - Must specify OCC using sequential version numbers / sequence IDs per account to detect and reject concurrent write conflicts.

5. **REQ-5: Snapshotting & Read Performance**
   - Must define periodic state snapshots (e.g. every N events or nightly) to prevent unbounded replay latency on aggregate reconstitution.

6. **REQ-6: Split-Brain & Partition Tolerance**
   - Must define consensus protocol (Raft/Paxos) or single-leader partition lease mechanism to ensure only one node appends events to an aggregate under network partitions.

7. **REQ-7: Backpressure & Flow Control**
   - Must address consumer lag and backpressure mechanisms (reactive streams, rate limiting, bounded consumer queues) between projection engines and event log.

8. **REQ-8: Schema Evolution & Versioning**
   - Must detail event schema evolution strategy (e.g. upcasters, Protocol Buffers backward compatibility, never mutating historical events).

9. **REQ-9: Eventual Consistency vs Read Model Synchronization**
   - Must clearly separate write-side consistency (ACID aggregate) from read-side projections (CQRS), handling read-after-write consistency for clients (e.g. version tokens).

10. **REQ-10: Compensation & Saga Pattern for Multi-Account Transfers**
    - Transfers between different accounts across partitions cannot share atomic locks; must use Saga orchestration/choreography with compensating reversal transactions.

11. **REQ-11: Observability & Auditability**
    - Must specify immutable audit log trails, cryptographic hash chaining (or tamper-evident event signing), and distributed tracing (W3C traceparent).

12. **REQ-12: Zero-Downtime Migration & Disaster Recovery**
    - Must specify active-passive or active-active DR strategy, RPO/RTO targets, and blue/green read projection rebuild without taking the write ledger offline.

## Scoring:
- Score = Covered / 12
- Penalties: -1 for hallucinations, -1 for dangerous distributed antipatterns (e.g. recommending 2-Phase Commit across asynchronous message brokers).
