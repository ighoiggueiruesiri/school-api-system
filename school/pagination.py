"""
school/pagination.py

Every list endpoint returns this shape:

{
  "count":    85,
  "pages":    5,
  "page":     1,
  "per_page": 20,
  "next":     "http://127.0.0.1:8000/api/students/?page=2",
  "previous": null,
  "results":  [...]
}

Frontend usage:
  First page:        GET /api/students/
  Next page:         GET /api/students/?page=2
  Bigger page size:  GET /api/students/?per_page=50
  Filter + paginate: GET /api/students/?classroom=2&page=3
"""

import math
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class StandardPagination(PageNumberPagination):
    page_size             = 20
    page_size_query_param = "per_page"   # caller can override: ?per_page=50
    max_page_size         = 100          # never return more than 100 at once

    def get_paginated_response(self, data):
        total_pages = math.ceil(
            self.page.paginator.count / self.get_page_size(self.request)
        )
        return Response({
            "count":    self.page.paginator.count,
            "pages":    total_pages,
            "page":     self.page.number,
            "per_page": self.get_page_size(self.request),
            "next":     self.get_next_link(),
            "previous": self.get_previous_link(),
            "results":  data,
        })

    def get_paginated_response_schema(self, schema):
        return {
            "type": "object",
            "properties": {
                "count":    {"type": "integer"},
                "pages":    {"type": "integer"},
                "page":     {"type": "integer"},
                "per_page": {"type": "integer"},
                "next":     {"type": "string", "nullable": True},
                "previous": {"type": "string", "nullable": True},
                "results":  schema,
            },
        }


class SmallPagination(StandardPagination):
    """10 per page — useful for mobile or dashboard widgets."""
    page_size = 10
