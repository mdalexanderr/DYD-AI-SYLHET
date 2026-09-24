"""Services — the layer between models and routes. plan.md §9.1.

WHY THIS LAYER EXISTS AT ALL
    A route should describe WHAT a page shows, not how to fetch it. More importantly,
    the rules that must never be broken — which participants may appear, what a
    statistic is allowed to reveal — belong in exactly ONE place. A template that
    queried the model directly would be a second place those rules are expressed, and
    the second place is always the one that drifts.

    `participant_service` owns the publication filter and the public projection.
    `stats_service` owns the `<5` suppression rule. Both are privacy boundaries, and
    both are tested as such.
"""
