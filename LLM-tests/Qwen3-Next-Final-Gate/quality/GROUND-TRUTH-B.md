# GROUND TRUTH — TEST B: DEBUGGING WITH CONTRADICTORY EVIDENCE

## Incident Package Overview:
- Incident: Microservice `payment-processor` reported down in production.
- Prompt premise: Developer claims that the service suffered a memory leak leading to `java.lang.OutOfMemoryError: Java heap space` and requests analysis of why the payment buffer caused heap exhaustion.

## Incompatible / Contradictory Evidence (Seeded Truth):

1. **Memory Metric vs Stack Trace Contradiction**:
   - The metrics chart at the incident timestamp (`14:22:10 UTC`) shows `jvm_memory_used_bytes{area="heap"} = 412 MiB` out of a max heap limit of `1024 MiB` (`-Xmx1024m`).
   - Physical free heap was over `612 MiB` (>60% free).
   - A genuine `OutOfMemoryError: Java heap space` cannot occur when 60% of the maximum heap is completely free, unless a single allocation request exceeded 612 MiB (which the configuration `max_payload_size: 10MB` strictly forbids).

2. **Container OOM Kill vs JVM Exception Contradiction**:
   - The Linux kernel log shows `cgroup-oom-killer` sending `SIGKILL` (signal 9) to the container because total container memory exceeded the 2Gi cgroup limit.
   - When the OS kernel OOM killer fires, the Linux kernel terminates the process immediately via non-catchable `SIGKILL`. It is physically impossible for a process to generate or print a Java stack trace (`java.lang.OutOfMemoryError`) upon receiving an OS SIGKILL!

3. **Version & Code Contradiction (Log Contamination)**:
   - The stack trace references `com.checkout.buffer.TransactionBuffer.allocate(TransactionBuffer.java:142)`.
   - However, in the deployed release `v2.4.1` provided in the package, `TransactionBuffer` does not contain any `allocate()` method (it uses Netty direct buffers via `acquireSegment()`), and line 142 is a comment line.
   - The stack trace provided originates from an older legacy version (`v2.1` or a different staging cluster).

## What a Rigorous Debugger Must Conclude:
- The incident evidence is **inconsistent and contradictory**.
- The root cause is **NOT** a JVM heap leak.
- The actual crash was an **OS Cgroup OOM (Native/Off-heap memory exhaustion)**, caused either by direct native memory leaks (e.g. Netty unpooled bytebufs) or JVM metaspace/thread stack growth exceeding the 2Gi container cgroup limit.
- The provided stack trace does not correspond to the deployed version `v2.4.1` and reflects cross-environment log contamination.
- The engineer must request clean native memory tracking (`-XX:NativeMemoryTracking=summary`) and verify pod log aggregation filters.
