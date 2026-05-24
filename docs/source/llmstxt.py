"""Sphinx extension: generate llms.txt and llms-full.txt on HTML build."""

from __future__ import annotations

from pathlib import Path

from sphinx.application import Sphinx

# (stem, title, description, optional)
_PAGES: list[tuple[str, str, str, bool]] = [
    (
        "index",
        "Overview",
        "Introduction, installation, quick start, and services overview",
        False,
    ),
    (
        "tutorial",
        "Tutorial",
        "Step-by-step guide building production asyncio services",
        False,
    ),
    (
        "modules",
        "Modules",
        "All built-in modules: threads, timeout, pool, circuit breaker, logging, signals",
        False,
    ),
    (
        "threads",
        "Threads",
        "Running blocking code in thread pools with @threaded and WorkerPool",
        False,
    ),
    (
        "timeout",
        "Timeout",
        "Deadline and timeout utilities for coroutines",
        False,
    ),
    (
        "pool",
        "Connection Pool",
        "Generic async connection pool implementation",
        False,
    ),
    (
        "worker_pool",
        "Worker Pool",
        "Process-based worker pool for CPU-bound tasks",
        False,
    ),
    (
        "process_pool",
        "Process Pool",
        "Low-level process pool and inter-process communication",
        False,
    ),
    (
        "circuit_breaker",
        "Circuit Breaker",
        "Circuit breaker pattern to prevent cascading failures",
        False,
    ),
    (
        "async_backoff",
        "Async Backoff",
        "asyncbackoff and asyncretry decorators for retry logic",
        False,
    ),
    (
        "context",
        "Context",
        "Dependency injection context for sharing objects across services",
        False,
    ),
    (
        "signal",
        "Signals",
        "Pre/post-start signal hooks for service coordination",
        False,
    ),
    (
        "entrypoint",
        "Entrypoint",
        "Event loop setup, logging configuration, and graceful shutdown",
        False,
    ),
    (
        "logging",
        "Logging",
        "Structured logging, log formats, and async log flushing",
        False,
    ),
    (
        "statistic",
        "Statistics",
        "Built-in metrics collection and exposition",
        False,
    ),
    (
        "aggregate",
        "Aggregate",
        "Aggregating and batching async operations",
        False,
    ),
    ("io", "I/O Utilities", "Async file and stream I/O helpers", False),
    (
        "utils",
        "Utilities",
        "Miscellaneous utility functions and helpers",
        False,
    ),
    (
        "services/index",
        "Services",
        "All built-in services: HTTP, TCP, UDP, CRON, ASGI, gRPC, and more",
        False,
    ),
    (
        "api/index",
        "API Reference",
        "Full autodoc API reference for all public classes and functions",
        False,
    ),
    (
        "pytest",
        "Pytest Plugin",
        "aiomisc pytest fixtures and plugin for async test support",
        True,
    ),
    (
        "plugins",
        "Plugins",
        "Optional integrations: uvloop, rich logging, carbon metrics",
        True,
    ),
]


def _page_link(stem: str, title: str, description: str, base_url: str) -> str:
    if stem in ("api/index", "services/index"):
        url = f"{base_url}{stem}.html"
    else:
        url = f"{base_url}_sources/{stem}.rst.txt"
    return f"- [{title}]({url}): {description}"


def _links_block(pages: list[tuple[str, str, str, bool]], base_url: str) -> str:
    essential = [(s, t, d) for s, t, d, opt in pages if not opt]
    optional = [(s, t, d) for s, t, d, opt in pages if opt]

    lines = [
        "## Docs source files split by topic for easier navigation and LLM processing:",
        "",
        "The links below point to the raw source of each documentation page",
        "(`/_sources/<topic>.rst.txt` on docs.aiomisc.com).",
        "Prefer these for LLM consumption: no HTML scaffolding, no navigation chrome,",
        "no JavaScript.",
        "",
        *(_page_link(s, t, d, base_url) for s, t, d in essential),
    ]
    if optional:
        lines += [
            "",
            "## Optional",
            "",
            *(_page_link(s, t, d, base_url) for s, t, d in optional),
        ]
    return "\n".join(lines)


def _on_build_finished(app: Sphinx, exception: Exception | None) -> None:
    if exception or app.builder.name != "html":
        return

    src_dir = Path(app.srcdir)
    out_dir = Path(app.outdir)
    base_url: str = app.config.html_baseurl or ""
    if base_url and not base_url.endswith("/"):
        base_url += "/"
    pages: list[tuple[str, str, str, bool]] = app.config.llms_pages

    project: str = app.config.project

    # --- llms.txt ---
    llms_txt = (
        f"# {project}\n\n"
        f"> {app.config.html_title or project}\n\n"
        f"{_links_block(pages, base_url)}\n"
    )
    (out_dir / "llms.txt").write_text(llms_txt, encoding="utf-8")

    # --- llms-full.txt ---
    parts: list[str] = []
    for stem, *_ in pages:
        rst = src_dir / f"{stem}.rst"
        if rst.exists():
            parts.append(rst.read_text(encoding="utf-8"))
    (out_dir / "llms-full.txt").write_text(
        "\n\n---\n\n".join(parts), encoding="utf-8"
    )


def setup(app: Sphinx) -> dict[str, object]:
    app.add_config_value("llms_pages", _PAGES, "html")
    app.connect("build-finished", _on_build_finished)
    return {
        "version": "0.1",
        "parallel_read_safe": True,
        "parallel_write_safe": True,
    }
