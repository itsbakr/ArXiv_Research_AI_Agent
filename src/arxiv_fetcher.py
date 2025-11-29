"""
ArXiv Fetcher Module

Fetches recent papers from arXiv across multiple CS categories.
"""

import arxiv
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field
from tenacity import retry, stop_after_attempt, wait_exponential


@dataclass
class Paper:
    """Represents an arXiv paper with relevant metadata."""
    
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    primary_category: str
    published: datetime
    updated: datetime
    arxiv_url: str
    pdf_url: str
    
    def to_dict(self) -> dict:
        """Convert paper to dictionary for serialization."""
        return {
            "arxiv_id": self.arxiv_id,
            "title": self.title,
            "authors": self.authors,
            "abstract": self.abstract,
            "categories": self.categories,
            "primary_category": self.primary_category,
            "published": self.published.isoformat(),
            "updated": self.updated.isoformat(),
            "arxiv_url": self.arxiv_url,
            "pdf_url": self.pdf_url,
        }


# Category mapping for human-readable names
CATEGORY_NAMES = {
    "cs.AI": "Artificial Intelligence",
    "cs.LG": "Machine Learning",
    "cs.CL": "Computation and Language",
    "cs.CV": "Computer Vision",
    "cs.RO": "Robotics",
}

# Default categories to monitor
DEFAULT_CATEGORIES = ["cs.AI", "cs.LG", "cs.CL", "cs.CV", "cs.RO"]


class ArxivFetcher:
    """Fetches and filters papers from arXiv."""
    
    def __init__(
        self,
        categories: list[str] = None,
        max_results_per_category: int = 50,
    ):
        """
        Initialize the arXiv fetcher.
        
        Args:
            categories: List of arXiv categories to monitor (e.g., ["cs.AI", "cs.LG"])
            max_results_per_category: Maximum papers to fetch per category
        """
        self.categories = categories or DEFAULT_CATEGORIES
        self.max_results_per_category = max_results_per_category
        self.client = arxiv.Client(
            page_size=100,
            delay_seconds=3.0,  # Be respectful to arXiv API
            num_retries=3,
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def fetch_recent_papers(
        self,
        days_back: int = 1,
        categories: list[str] = None,
    ) -> list[Paper]:
        """
        Fetch recent papers from arXiv.
        
        Args:
            days_back: How many days back to look for papers
            categories: Override default categories for this fetch
            
        Returns:
            List of Paper objects
        """
        categories = categories or self.categories
        all_papers: dict[str, Paper] = {}  # Use dict to deduplicate by arxiv_id
        
        for category in categories:
            papers = self._fetch_category(category, days_back)
            for paper in papers:
                # Deduplicate - papers can appear in multiple categories
                if paper.arxiv_id not in all_papers:
                    all_papers[paper.arxiv_id] = paper
        
        # Sort by published date (newest first)
        sorted_papers = sorted(
            all_papers.values(),
            key=lambda p: p.published,
            reverse=True,
        )
        
        print(f"Fetched {len(sorted_papers)} unique papers across {len(categories)} categories")
        return sorted_papers
    
    def _fetch_category(self, category: str, days_back: int) -> list[Paper]:
        """Fetch papers from a specific category."""
        # Build search query for recent papers in this category
        search = arxiv.Search(
            query=f"cat:{category}",
            max_results=self.max_results_per_category,
            sort_by=arxiv.SortCriterion.SubmittedDate,
            sort_order=arxiv.SortOrder.Descending,
        )
        
        papers = []
        cutoff_date = datetime.now() - timedelta(days=days_back + 1)  # +1 for timezone buffer
        
        try:
            for result in self.client.results(search):
                # Filter by date - only include papers from the last N days
                # Note: arxiv published dates are timezone-naive
                published_date = result.published.replace(tzinfo=None)
                if published_date < cutoff_date:
                    continue
                
                paper = Paper(
                    arxiv_id=result.entry_id.split("/")[-1],  # Extract ID from URL
                    title=result.title.replace("\n", " ").strip(),
                    authors=[author.name for author in result.authors],
                    abstract=result.summary.replace("\n", " ").strip(),
                    categories=result.categories,
                    primary_category=result.primary_category,
                    published=result.published,
                    updated=result.updated,
                    arxiv_url=result.entry_id,
                    pdf_url=result.pdf_url,
                )
                papers.append(paper)
                
        except Exception as e:
            print(f"Error fetching category {category}: {e}")
            raise
        
        print(f"  {category}: {len(papers)} papers")
        return papers
    
    def fetch_todays_papers(self) -> list[Paper]:
        """Convenience method to fetch today's papers."""
        return self.fetch_recent_papers(days_back=1)
    
    def get_category_name(self, category_code: str) -> str:
        """Get human-readable name for a category code."""
        return CATEGORY_NAMES.get(category_code, category_code)


# For direct testing
if __name__ == "__main__":
    fetcher = ArxivFetcher()
    papers = fetcher.fetch_todays_papers()
    
    print(f"\n{'='*60}")
    print(f"Found {len(papers)} papers")
    print(f"{'='*60}\n")
    
    for i, paper in enumerate(papers[:5], 1):
        print(f"{i}. {paper.title}")
        print(f"   Authors: {', '.join(paper.authors[:3])}{'...' if len(paper.authors) > 3 else ''}")
        print(f"   Category: {paper.primary_category}")
        print(f"   URL: {paper.arxiv_url}")
        print()

