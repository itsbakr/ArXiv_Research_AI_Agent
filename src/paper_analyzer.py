"""
Paper Analyzer Module

Uses Claude to analyze, rank, and summarize arXiv papers by innovation.
"""

import os
import json
from typing import Optional
from dataclasses import dataclass
from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from .arxiv_fetcher import Paper, CATEGORY_NAMES


@dataclass
class AnalyzedPaper:
    """A paper that has been analyzed by Claude."""
    
    paper: Paper
    innovation_score: int  # 1-10
    summary: str
    key_innovation: str
    implementation_details: str
    problem_solved: str
    potential_impact: str
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            **self.paper.to_dict(),
            "innovation_score": self.innovation_score,
            "summary": self.summary,
            "key_innovation": self.key_innovation,
            "implementation_details": self.implementation_details,
            "problem_solved": self.problem_solved,
            "potential_impact": self.potential_impact,
        }


class PaperAnalyzer:
    """Analyzes papers using Claude to identify the most innovative ones."""
    
    def __init__(
        self,
        api_key: str = None,
        model: str = None,
    ):
        """
        Initialize the paper analyzer.
        
        Args:
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            model: Claude model to use (defaults to CLAUDE_MODEL env var or claude-sonnet-4-20250514)
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable is required")
        
        self.model = model or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
        self.client = Anthropic(api_key=self.api_key)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def analyze_papers(
        self,
        papers: list[Paper],
        max_papers: int = 15,
    ) -> list[AnalyzedPaper]:
        """
        Analyze papers and return the most innovative ones with summaries.
        
        Args:
            papers: List of papers to analyze
            max_papers: Maximum number of top papers to return
            
        Returns:
            List of AnalyzedPaper objects, sorted by innovation score
        """
        if not papers:
            return []
        
        print(f"Analyzing {len(papers)} papers with Claude...")
        
        # First pass: rank papers by innovation
        ranked_paper_ids = self._rank_papers_by_innovation(papers, max_papers)
        
        # Get the top papers - match by ID prefix (without version suffix)
        # Claude may return "2511.21692" but paper.arxiv_id is "2511.21692v1"
        paper_map = {p.arxiv_id: p for p in papers}
        paper_map_no_version = {p.arxiv_id.split('v')[0]: p for p in papers}
        
        top_papers = []
        for pid in ranked_paper_ids:
            if pid in paper_map:
                top_papers.append(paper_map[pid])
            elif pid in paper_map_no_version:
                top_papers.append(paper_map_no_version[pid])
        
        print(f"Selected {len(top_papers)} most innovative papers for detailed analysis")
        
        # Second pass: generate detailed summaries for top papers
        analyzed_papers = self._generate_detailed_summaries(top_papers)
        
        # Sort by innovation score (highest first)
        analyzed_papers.sort(key=lambda p: p.innovation_score, reverse=True)
        
        return analyzed_papers
    
    def _rank_papers_by_innovation(
        self,
        papers: list[Paper],
        top_n: int,
    ) -> list[str]:
        """Use Claude to rank papers by innovation and return top N paper IDs."""
        
        # Prepare papers summary for Claude
        papers_text = self._format_papers_for_ranking(papers)
        
        prompt = f"""You are an AI research expert tasked with identifying the most innovative and impactful papers from today's arXiv submissions.

Below are {len(papers)} recent papers from arXiv. Analyze them and select the {top_n} MOST INNOVATIVE papers based on:

1. **Novelty**: Does it introduce genuinely new ideas, methods, or perspectives?
2. **Technical Contribution**: Is the technical approach sophisticated and well-designed?
3. **Potential Impact**: Could this significantly influence the field or enable new applications?
4. **Practical Value**: Does it solve real problems or enable new capabilities?

PAPERS TO ANALYZE:
{papers_text}

IMPORTANT: Return ONLY a JSON array of arXiv IDs for the top {top_n} most innovative papers, ordered from most to least innovative.

Example format:
["2411.12345", "2411.67890", "2411.11111"]

Return ONLY the JSON array, no other text."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        
        response_text = response.content[0].text.strip()
        
        # Parse the JSON response
        try:
            # Handle potential markdown code blocks
            if "```" in response_text:
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            ranked_ids = json.loads(response_text)
            return ranked_ids[:top_n]
        except json.JSONDecodeError as e:
            print(f"Error parsing Claude response: {e}")
            print(f"Response was: {response_text}")
            # Fallback: return first N papers
            return [p.arxiv_id for p in papers[:top_n]]
    
    def _format_papers_for_ranking(self, papers: list[Paper]) -> str:
        """Format papers into a condensed text for ranking."""
        lines = []
        for paper in papers:
            category_name = CATEGORY_NAMES.get(paper.primary_category, paper.primary_category)
            # Truncate abstract for initial ranking
            abstract_preview = paper.abstract[:500] + "..." if len(paper.abstract) > 500 else paper.abstract
            lines.append(f"""
---
ID: {paper.arxiv_id}
Title: {paper.title}
Category: {category_name}
Authors: {', '.join(paper.authors[:5])}{'...' if len(paper.authors) > 5 else ''}
Abstract: {abstract_preview}
---""")
        return "\n".join(lines)
    
    def _generate_detailed_summaries(
        self,
        papers: list[Paper],
    ) -> list[AnalyzedPaper]:
        """Generate detailed summaries for selected papers."""
        
        analyzed = []
        
        for paper in papers:
            try:
                analysis = self._analyze_single_paper(paper)
                analyzed.append(analysis)
            except Exception as e:
                print(f"Error analyzing paper {paper.arxiv_id}: {e}")
                continue
        
        return analyzed
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def _analyze_single_paper(self, paper: Paper) -> AnalyzedPaper:
        """Generate detailed analysis for a single paper."""
        
        category_name = CATEGORY_NAMES.get(paper.primary_category, paper.primary_category)
        
        prompt = f"""Analyze this arXiv paper and provide a detailed summary:

TITLE: {paper.title}
AUTHORS: {', '.join(paper.authors)}
CATEGORY: {category_name}
ARXIV ID: {paper.arxiv_id}

ABSTRACT:
{paper.abstract}

Provide your analysis in the following JSON format:
{{
    "innovation_score": <1-10 integer rating>,
    "summary": "<2-3 sentence executive summary>",
    "problem_solved": "<What problem does this paper address?>",
    "key_innovation": "<What is the main novel contribution?>",
    "implementation_details": "<How did they implement/achieve this? Key technical details>",
    "potential_impact": "<What is the potential impact on the field?>"
}}

Be specific and technical in your analysis. Return ONLY the JSON object."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        
        response_text = response.content[0].text.strip()
        
        # Parse JSON response
        try:
            # Handle potential markdown code blocks
            if "```" in response_text:
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
            
            analysis = json.loads(response_text)
            
            return AnalyzedPaper(
                paper=paper,
                innovation_score=int(analysis.get("innovation_score", 5)),
                summary=analysis.get("summary", ""),
                key_innovation=analysis.get("key_innovation", ""),
                implementation_details=analysis.get("implementation_details", ""),
                problem_solved=analysis.get("problem_solved", ""),
                potential_impact=analysis.get("potential_impact", ""),
            )
            
        except json.JSONDecodeError as e:
            print(f"Error parsing analysis for {paper.arxiv_id}: {e}")
            # Return with default values
            return AnalyzedPaper(
                paper=paper,
                innovation_score=5,
                summary=paper.abstract[:300] + "...",
                key_innovation="See abstract for details",
                implementation_details="See paper for technical details",
                problem_solved="See abstract",
                potential_impact="To be determined",
            )
    
    def generate_daily_summary(
        self,
        analyzed_papers: list[AnalyzedPaper],
        date_str: str,
    ) -> str:
        """Generate an executive daily summary of all analyzed papers."""
        
        if not analyzed_papers:
            return f"# ArXiv AI Research Summary - {date_str}\n\nNo significant papers found today."
        
        # Group papers by category
        by_category: dict[str, list[AnalyzedPaper]] = {}
        for ap in analyzed_papers:
            cat = ap.paper.primary_category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(ap)
        
        prompt = f"""Create an engaging executive summary for today's most innovative AI research papers.

Date: {date_str}
Total Papers Analyzed: {len(analyzed_papers)}

PAPERS BY CATEGORY:
"""
        for cat, papers in by_category.items():
            cat_name = CATEGORY_NAMES.get(cat, cat)
            prompt += f"\n## {cat_name}\n"
            for ap in papers:
                prompt += f"""
- **{ap.paper.title}** (Score: {ap.innovation_score}/10)
  Key Innovation: {ap.key_innovation}
  Impact: {ap.potential_impact}
"""

        prompt += """

Generate a Notion-flavored Markdown summary with:
1. A brief executive overview (2-3 sentences about today's trends)
2. Top 3 most exciting papers with why they matter
3. Category-by-category highlights
4. Key themes and emerging trends observed

Make it engaging and insightful for researchers and practitioners. Use markdown formatting.
Return ONLY the markdown content, no code blocks."""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        
        return response.content[0].text.strip()


# For direct testing
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    from .arxiv_fetcher import ArxivFetcher
    
    # Fetch some papers
    fetcher = ArxivFetcher(max_results_per_category=10)
    papers = fetcher.fetch_todays_papers()
    
    if papers:
        # Analyze them
        analyzer = PaperAnalyzer()
        analyzed = analyzer.analyze_papers(papers, max_papers=5)
        
        print(f"\n{'='*60}")
        print(f"Top {len(analyzed)} Most Innovative Papers")
        print(f"{'='*60}\n")
        
        for i, ap in enumerate(analyzed, 1):
            print(f"{i}. [{ap.innovation_score}/10] {ap.paper.title}")
            print(f"   Summary: {ap.summary}")
            print(f"   Innovation: {ap.key_innovation}")
            print()

