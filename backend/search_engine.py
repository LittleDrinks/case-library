#!/usr/bin/env python3
"""Search and recommendation helpers."""

from typing import Dict, List, Optional

from database import (
    filter_cases,
    get_latest_cases,
    get_recommendation_candidates,
    get_trending_cases,
    search_cases,
)


class CaseSearchEngine:
    def search(self, query: str, status: Optional[str] = "approved", limit: int = 20) -> List[Dict]:
        return search_cases(query, status=status, limit=limit)

    def get_recommendations(self, case_id: int, limit: int = 5) -> List[Dict]:
        return get_recommendation_candidates(case_id, limit)

    def get_trending(self, limit: int = 10) -> List[Dict]:
        return get_trending_cases(limit)

    def get_latest(self, limit: int = 10) -> List[Dict]:
        return get_latest_cases(limit)

    def advanced_filter(
        self,
        type_filter: Optional[str] = None,
        theme_filter: Optional[str] = None,
        status_filter: str = "approved",
        keyword_filter: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict]:
        return filter_cases(
            type_filter=type_filter,
            theme_filter=theme_filter,
            status_filter=status_filter,
            keyword_filter=keyword_filter,
            limit=limit,
        )


if __name__ == "__main__":
    print("Search engine loaded")
