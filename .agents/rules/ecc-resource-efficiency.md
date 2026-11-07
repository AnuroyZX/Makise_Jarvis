---
trigger: always_on
description: "ECC Resource Efficiency & Low-RAM Optimization Rules for Modest PCs"
---

# ECC Resource Efficiency Rules (Foreground vs. Background Eco-Core)

1. **Lazy Loading of Heavy Modules**:
   - Never import heavy optional dependencies (e.g., browser automation, audio codecs, GUI frameworks) at top-level startup. Import them lazily inside the specific method when invoked.

2. **Memory Footprint Discipline**:
   - Use `@dataclass(slots=True)` for frequent in-memory objects (messages, memory records, tool results, app entries).
   - Bound all in-memory queues and caches (`collections.deque(maxlen=...)`).
   - Share a single `httpx.AsyncClient` pool across cloud modules when active, and close idle connections when transitioning to `BACKGROUND_ECO`.

3. **Ephemeral Subprocesses & UI**:
   - Any external heavy resource (such as an interactive browser or the local Onboarding/Settings Web UI) must have an idle timeout watchdog (default 120s) that terminates the process and invokes `ResourceGovernor.trim_working_set()`.

4. **Adaptive Polling**:
   - Background gateways must dynamically scale polling intervals based on `PowerMode` (`FOREGROUND_ACTIVE` vs `BACKGROUND_ECO`).
