"""
app/metrics.py

Prometheus metric singletons and the ``record_metrics()`` helper.

Three module-level singletons are registered against the default global
registry exactly once at import time, preventing duplicate-registration
errors when the module is imported multiple times.

For test isolation, ``record_metrics()`` accepts an optional *registry*
keyword argument.  When provided, the function creates fresh
Counter/Histogram instances bound to that registry (a ``CollectorRegistry``
per-test) rather than mutating the global singletons.  This keeps test
counters completely independent of one another and of the application
process's global state.

Requirements: US-3.2, US-3.3, US-3.4, US-3.5
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram, CollectorRegistry

# ---------------------------------------------------------------------------
# Module-level singletons (global registry)
# ---------------------------------------------------------------------------

#: Total HTTP requests, labelled by method / route / HTTP status code.
REQUEST_COUNT: Counter = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "route", "status"],
)

#: Total HTTP errors (5xx only), labelled by method / route.
ERROR_COUNT: Counter = Counter(
    "http_errors_total",
    "Total HTTP errors",
    ["method", "route"],
)

#: HTTP request duration histogram, labelled by method / route.
REQUEST_LATENCY: Histogram = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "route"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10],
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

_LATENCY_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]


def record_metrics(
    method: str,
    route: str,
    status_code: int,
    duration: float,
    *,
    registry: CollectorRegistry | None = None,
) -> None:
    """Record one HTTP request's worth of metrics.

    Parameters
    ----------
    method:
        HTTP verb, e.g. ``"GET"``.
    route:
        Matched Flask URL rule, e.g. ``"/health"``.
    status_code:
        Integer HTTP response status code.
    duration:
        Request wall-clock time in seconds.
    registry:
        Optional :class:`prometheus_client.CollectorRegistry`.  When
        supplied (typically in tests), fresh metric objects are created
        against that registry so each test has an isolated counter space.
        When ``None`` (the default), the module-level singletons
        registered against the global ``prometheus_client.REGISTRY`` are
        used.
    """
    if registry is None:
        # --- production path: use module-level singletons ---
        REQUEST_COUNT.labels(
            method=method,
            route=route,
            status=str(status_code),
        ).inc()

        if status_code >= 500:
            ERROR_COUNT.labels(method=method, route=route).inc()

        REQUEST_LATENCY.labels(method=method, route=route).observe(duration)
    else:
        # --- test-isolation path: create fresh instances per registry ---
        # prometheus_client raises if a metric with the same name is
        # registered twice in the same registry, so we re-use whatever
        # is already there if it exists.
        try:
            req_count: Counter = Counter(
                "http_requests_total",
                "Total HTTP requests",
                ["method", "route", "status"],
                registry=registry,
            )
        except ValueError:
            # Already registered in this registry — look it up.
            req_count = registry._names_to_collectors.get(  # type: ignore[attr-defined]
                "http_requests_total"
            )

        try:
            err_count: Counter = Counter(
                "http_errors_total",
                "Total HTTP errors",
                ["method", "route"],
                registry=registry,
            )
        except ValueError:
            err_count = registry._names_to_collectors.get(  # type: ignore[attr-defined]
                "http_errors_total"
            )

        try:
            latency: Histogram = Histogram(
                "http_request_duration_seconds",
                "HTTP request duration",
                ["method", "route"],
                buckets=_LATENCY_BUCKETS,
                registry=registry,
            )
        except ValueError:
            latency = registry._names_to_collectors.get(  # type: ignore[attr-defined]
                "http_request_duration_seconds"
            )

        req_count.labels(
            method=method,
            route=route,
            status=str(status_code),
        ).inc()

        if status_code >= 500:
            err_count.labels(method=method, route=route).inc()

        latency.labels(method=method, route=route).observe(duration)
