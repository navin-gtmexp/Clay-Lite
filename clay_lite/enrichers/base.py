"""Abstract base class for company enrichers."""

from abc import ABC, abstractmethod

from ..models import Company


class CompanyEnricher(ABC):
    """Base class for enrichment modules that add data to Company objects."""

    @abstractmethod
    def enrich(self, company: Company) -> Company:
        """
        Enrich a company with additional data.
        Must not raise — log errors to company.enrichment_errors and return the company.
        """
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this enricher."""
        ...
