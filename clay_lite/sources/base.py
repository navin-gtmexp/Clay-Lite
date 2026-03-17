"""Abstract base class for company data sources."""

from abc import ABC, abstractmethod

from ..models import Company, FilterConfig


class CompanySource(ABC):
    """Base class for all company search sources."""

    @abstractmethod
    def search(self, filters: FilterConfig, max_results: int) -> list:
        """
        Search for companies matching the given filters.

        Returns a list of Company objects (up to max_results).
        Should never raise — log errors and return partial results.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this source (e.g. 'apollo', 'csv')."""
        ...

    def _apply_post_filters(self, companies: list, filters: FilterConfig) -> list:
        """
        Apply filters that couldn't be handled server-side.
        Called by subclasses after fetching raw results.
        """
        result = []
        for c in companies:
            if filters.hq_country and c.hq_country:
                if c.hq_country.upper() not in [x.upper() for x in filters.hq_country]:
                    continue

            if filters.employee_count_min is not None and c.employee_count is not None:
                if c.employee_count < filters.employee_count_min:
                    continue

            if filters.employee_count_max is not None and c.employee_count is not None:
                if c.employee_count > filters.employee_count_max:
                    continue

            if filters.revenue_usd_min is not None and c.revenue_usd is not None:
                if c.revenue_usd < filters.revenue_usd_min:
                    continue

            if filters.revenue_usd_max is not None and c.revenue_usd is not None:
                if c.revenue_usd > filters.revenue_usd_max:
                    continue

            if filters.min_customer_count is not None and c.customer_count is not None:
                if c.customer_count < filters.min_customer_count:
                    continue

            result.append(c)
        return result
