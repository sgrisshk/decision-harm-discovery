"""Registered domains for TASK-061's multi-domain benchmark family.

Add a domain here once its module exposes a `SPEC: DomainSpec` — the parameterized test suite
(`tests/analytics/test_domain_benchmarks.py`) and `scripts/generate_domain_benchmark.py`
automatically pick up every registered domain, no per-domain test/CLI code required.
"""

from __future__ import annotations

from policy_analytics.domain_benchmarks import b2b_sales, ecommerce, insurance, manufacturing, saas
from policy_analytics.domain_benchmarks.common import DomainSpec

DOMAIN_REGISTRY: dict[str, DomainSpec] = {
    ecommerce.DOMAIN_ID: ecommerce.SPEC,
    saas.DOMAIN_ID: saas.SPEC,
    insurance.DOMAIN_ID: insurance.SPEC,
    manufacturing.DOMAIN_ID: manufacturing.SPEC,
    b2b_sales.DOMAIN_ID: b2b_sales.SPEC,
}
