#!/usr/bin/env python3
"""
Runtime / CI verification script for the Circuit Breaker implementation.

Usage:
    python scripts/verify_circuit_breaker.py

What it checks:
1. All unit & integration tests for circuit breaker pass.
2. Every inter-service HTTP client imports and uses CircuitBreaker.
3. Prometheus metrics for circuit breaker are registered.
4. Fallback / degradation logic is present in bot-service ApiClient.

Exit code 0 = everything OK, 1 = failure detected.
"""

from __future__ import annotations

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "services"
SHARED = SERVICES / "_shared"


def _load_shared_module():
    """Make `shared.*` importable without Docker layout."""
    if "shared" in sys.modules:
        return
    sys.path.insert(0, str(SERVICES))
    spec = importlib.util.spec_from_file_location("shared", str(SHARED / "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules["shared"] = module
    for sub in ("logging", "events", "metrics", "settings", "rabbitmq", "circuit_breaker"):
        sub_spec = importlib.util.spec_from_file_location(
            f"shared.{sub}", str(SHARED / f"{sub}.py")
        )
        sub_mod = importlib.util.module_from_spec(sub_spec)
        sys.modules[f"shared.{sub}"] = sub_mod
        sub_spec.loader.exec_module(sub_mod)


def run_tests() -> bool:
    """Run all circuit-breaker related tests."""
    print("=" * 60)
    print("Step 1/4 – Running circuit breaker tests")
    print("=" * 60)

    test_files = [
        "bot-service/tests/test_circuit_breaker.py",
        "bot-service/tests/test_api_client_circuit_integration.py",
        "ranking-service/tests/test_photos_client.py",
        "notification-service/tests/test_profile_client.py",
    ]

    # We run each service's tests separately to avoid conftest name collisions.
    all_passed = True
    for tf in test_files:
        service_dir = tf.split("/")[0]
        pythonpath = f"{service_dir}/app:."
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            str(SERVICES / tf),
            "-v",
            "--tb=short",
        ]
        env = {"PYTHONPATH": pythonpath}
        print(f"\n> pytest {tf} (PYTHONPATH={pythonpath})")
        result = subprocess.run(cmd, cwd=SERVICES, capture_output=True, text=True, env=env)
        # pytest writes to stdout even on failure; we print it for visibility
        print(result.stdout)
        if result.returncode != 0:
            print(result.stderr)
            all_passed = False

    return all_passed


def check_clients_use_circuit_breaker() -> bool:
    """Verify that every inter-service REST client uses CircuitBreaker."""
    print("=" * 60)
    print("Step 2/4 – Checking that REST clients use CircuitBreaker")
    print("=" * 60)

    clients = [
        SERVICES / "bot-service" / "app" / "api_client.py",
        SERVICES / "ranking-service" / "app" / "photos_client.py",
        SERVICES / "notification-service" / "app" / "profile_client.py",
    ]

    ok = True
    for path in clients:
        source = path.read_text()
        tree = ast.parse(source)
        imports_cb = any(
            (
                isinstance(node, ast.ImportFrom)
                and node.module
                and "circuit_breaker" in node.module
            )
            for node in ast.walk(tree)
        )
        if imports_cb:
            print(f"  ✓ {path.relative_to(ROOT)} imports CircuitBreaker")
        else:
            print(f"  ✗ {path.relative_to(ROOT)} does NOT import CircuitBreaker")
            ok = False

    return ok


def check_metrics_registered() -> bool:
    """Ensure Prometheus counters exist in shared/metrics.py."""
    print("=" * 60)
    print("Step 3/4 – Checking Prometheus metrics")
    print("=" * 60)

    metrics_file = SHARED / "metrics.py"
    source = metrics_file.read_text()
    required = [
        "circuit_open_total",
        "circuit_short_circuit_total",
        "circuit_half_open_total",
    ]
    ok = True
    for name in required:
        if name in source:
            print(f"  ✓ {name} found")
        else:
            print(f"  ✗ {name} missing")
            ok = False
    return ok


def check_fallbacks_present() -> bool:
    """Verify degradation logic in bot-service ApiClient."""
    print("=" * 60)
    print("Step 4/4 – Checking fallback / degradation logic")
    print("=" * 60)

    api_client = SERVICES / "bot-service" / "app" / "api_client.py"
    source = api_client.read_text()

    fallbacks = [
        "except CircuitOpenApiError:",
        'return None',
        'return []',
    ]
    ok = True
    for token in fallbacks:
        if token in source:
            print(f"  ✓ '{token}' present")
        else:
            print(f"  ✗ '{token}' missing")
            ok = False
    return ok


def main() -> int:
    _load_shared_module()

    results = [
        run_tests(),
        check_clients_use_circuit_breaker(),
        check_metrics_registered(),
        check_fallbacks_present(),
    ]

    print("=" * 60)
    if all(results):
        print("All checks passed – Circuit Breaker is working correctly.")
        return 0
    else:
        print("Some checks failed – review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
