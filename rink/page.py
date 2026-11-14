"""The shape every listing answers in, so no client needs to know a source."""

def page_payload(items, page, per_page, total=None, total_pages=None):
    return {
        "items": items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }

