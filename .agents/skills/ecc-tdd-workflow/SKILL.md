---
name: ecc-tdd-workflow
description: "ECC Test-Driven Development (TDD) workflow for verifying all 9 modules with fast, isolated async unit tests and resource checks."
---

# ECC TDD & Verification Workflow

When implementing or modifying any module in Amadeus Kurisu:

1. **Design Interface & Contracts**:
   - Define the data models (`slots=True`) and protocol/interface for the module.
2. **Write Unit & Integration Tests**:
   - Ensure every module (1 through 9) has deterministic tests in `tests/` using `pytest` and `pytest-asyncio` without requiring live paid API calls (use mock transports or in-memory SQLite).
3. **Run Verification & Resource Check**:
   - Run `pytest tests/ -v` and verify 100% pass rate.
   - Verify memory footprint and Windows Working Set trimming via `ResourceGovernor`.
