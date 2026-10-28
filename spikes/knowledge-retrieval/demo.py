"""Run a fixed synthetic search -> replacement -> withdrawal demonstration."""
from datetime import datetime, timedelta, timezone
import json

from retrieval import Scope, Source, SyntheticRetrieval, SyntheticSources


def main() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    scope = Scope("synthetic", "handbook", "fake-owner", "reference")
    sources = SyntheticSources()
    sources.publish(Source(scope, "demo-guide", 1, "合成资料\n借阅期限为七天。",
                           now, now + timedelta(days=30)))
    retrieval = SyntheticRetrieval(sources, scope)
    retrieval.rebuild(now)
    result = retrieval.search(scope, "借阅", now)
    item = result.evidence[0]
    print(json.dumps({"step": "search", "status": result.status,
                      "excerpt": item.excerpt, "document": item.citation.document,
                      "version": item.citation.version, "line": item.citation.line},
                     ensure_ascii=False))
    sources.publish(Source(scope, "demo-guide", 2, "合成资料\n借阅期限为十四天。",
                           now, now + timedelta(days=30), supersedes=1))
    print(json.dumps({"step": "old-result", "status": retrieval.validate(scope, result, now).status}))
    retrieval.rebuild(now)
    updated = retrieval.search(scope, "借阅", now)
    print(json.dumps({"step": "rebuilt", "excerpt": updated.evidence[0].excerpt}, ensure_ascii=False))
    sources.revoke(scope, "demo-guide")
    print(json.dumps({"step": "withdrawn", "status": retrieval.validate(scope, updated, now).status}))
    print(json.dumps({"step": "search-after-withdrawal", "status": retrieval.search(scope, "借阅", now).status}))


if __name__ == "__main__":
    main()
