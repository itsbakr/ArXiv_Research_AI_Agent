"""
ArXiv AI Research Agent - Main Orchestrator

This script orchestrates the full pipeline:
1. Fetch recent papers from arXiv
2. Analyze and rank papers using Claude
3. Add top papers to Notion database
4. Create daily summary page
"""

import os
import sys
from datetime import datetime
from dotenv import load_dotenv

from .arxiv_fetcher import ArxivFetcher
from .paper_analyzer import PaperAnalyzer
from .notion_client import NotionClient


def run_daily_pipeline(
    days_back: int = 1,
    max_papers: int = 15,
    dry_run: bool = False,
) -> dict:
    """
    Run the complete daily pipeline.
    
    Args:
        days_back: How many days of papers to fetch
        max_papers: Maximum number of top papers to analyze in detail
        dry_run: If True, skip Notion operations (for testing)
        
    Returns:
        Dictionary with run statistics
    """
    stats = {
        "papers_fetched": 0,
        "papers_analyzed": 0,
        "papers_added": 0,
        "summary_created": False,
        "errors": [],
    }
    
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"\n{'='*60}")
    print(f"ArXiv AI Research Agent - {today}")
    print(f"{'='*60}\n")
    
    # Step 1: Fetch papers from arXiv
    print("Step 1: Fetching papers from arXiv...")
    print("-" * 40)
    
    try:
        fetcher = ArxivFetcher(max_results_per_category=50)
        papers = fetcher.fetch_recent_papers(days_back=days_back)
        stats["papers_fetched"] = len(papers)
        print(f"\nFetched {len(papers)} unique papers\n")
    except Exception as e:
        error_msg = f"Error fetching papers: {e}"
        print(error_msg)
        stats["errors"].append(error_msg)
        return stats
    
    if not papers:
        print("No papers found. Exiting.")
        return stats
    
    # Step 2: Analyze papers with Claude
    print("Step 2: Analyzing papers with Claude...")
    print("-" * 40)
    
    try:
        analyzer = PaperAnalyzer()
        analyzed_papers = analyzer.analyze_papers(papers, max_papers=max_papers)
        stats["papers_analyzed"] = len(analyzed_papers)
        print(f"\nAnalyzed {len(analyzed_papers)} top papers\n")
    except Exception as e:
        error_msg = f"Error analyzing papers: {e}"
        print(error_msg)
        stats["errors"].append(error_msg)
        return stats
    
    if not analyzed_papers:
        print("No papers passed analysis. Exiting.")
        return stats
    
    # Print summary of top papers
    print("Top Papers by Innovation Score:")
    print("-" * 40)
    for i, ap in enumerate(analyzed_papers[:5], 1):
        print(f"{i}. [{ap.innovation_score}/10] {ap.paper.title[:60]}...")
    print()
    
    if dry_run:
        print("DRY RUN: Skipping Notion operations\n")
        return stats
    
    # Step 3: Add papers to Notion database
    print("Step 3: Adding papers to Notion database...")
    print("-" * 40)
    
    try:
        notion = NotionClient()
        page_ids = notion.add_papers_to_database(analyzed_papers)
        stats["papers_added"] = len(page_ids)
        print(f"\nAdded {len(page_ids)} new papers to database\n")
    except Exception as e:
        error_msg = f"Error adding papers to Notion: {e}"
        print(error_msg)
        stats["errors"].append(error_msg)
    
    # Step 4: Create daily summary page
    print("Step 4: Creating daily summary page...")
    print("-" * 40)
    
    try:
        # Generate summary content
        summary_content = analyzer.generate_daily_summary(analyzed_papers, today)
        
        # Create the page
        summary_page_id = notion.create_daily_summary_page(
            date_str=today,
            summary_content=summary_content,
            papers=analyzed_papers,
        )
        stats["summary_created"] = summary_page_id is not None
        
        if summary_page_id:
            print(f"Created summary page: {summary_page_id}\n")
    except Exception as e:
        error_msg = f"Error creating summary page: {e}"
        print(error_msg)
        stats["errors"].append(error_msg)
    
    # Final summary
    print("="*60)
    print("Pipeline Complete!")
    print("="*60)
    print(f"Papers fetched:  {stats['papers_fetched']}")
    print(f"Papers analyzed: {stats['papers_analyzed']}")
    print(f"Papers added:    {stats['papers_added']}")
    print(f"Summary created: {'Yes' if stats['summary_created'] else 'No'}")
    
    if stats["errors"]:
        print(f"\nErrors encountered: {len(stats['errors'])}")
        for error in stats["errors"]:
            print(f"  - {error}")
    
    print()
    return stats


def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()
    
    # Check required environment variables
    required_vars = ["ANTHROPIC_API_KEY", "NOTION_API_KEY"]
    missing = [var for var in required_vars if not os.getenv(var)]
    
    if missing:
        print(f"Error: Missing required environment variables: {', '.join(missing)}")
        print("Please set these in your .env file or environment.")
        sys.exit(1)
    
    # Check for database ID - warn if not set
    if not os.getenv("NOTION_DATABASE_ID"):
        print("Warning: NOTION_DATABASE_ID not set. Papers will not be added to database.")
        print("Please set this after creating the database.\n")
    
    if not os.getenv("NOTION_PARENT_PAGE_ID"):
        print("Warning: NOTION_PARENT_PAGE_ID not set. Daily summaries will not be created.")
        print("Please set this to the ID of your ArXiv AI Research Agent page.\n")
    
    # Parse command line arguments
    dry_run = "--dry-run" in sys.argv
    
    # Check for days argument
    days_back = 1
    for arg in sys.argv:
        if arg.startswith("--days="):
            try:
                days_back = int(arg.split("=")[1])
            except ValueError:
                pass
    
    # Check for max papers argument
    max_papers = 15
    for arg in sys.argv:
        if arg.startswith("--max="):
            try:
                max_papers = int(arg.split("=")[1])
            except ValueError:
                pass
    
    # Run the pipeline
    stats = run_daily_pipeline(
        days_back=days_back,
        max_papers=max_papers,
        dry_run=dry_run,
    )
    
    # Exit with error code if there were errors
    if stats["errors"]:
        sys.exit(1)


if __name__ == "__main__":
    main()

