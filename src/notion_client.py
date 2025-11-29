"""
Notion Client Module

Handles all Notion operations: adding papers to database and creating daily summary pages.
Uses the official Notion API.
"""

import os
import requests
from datetime import datetime
from typing import Optional
from dataclasses import dataclass
from tenacity import retry, stop_after_attempt, wait_exponential

from .paper_analyzer import AnalyzedPaper
from .arxiv_fetcher import CATEGORY_NAMES


# Notion API base URL
NOTION_API_BASE = "https://api.notion.com/v1"
NOTION_API_VERSION = "2022-06-28"


# Category code to Notion select value mapping
CATEGORY_TO_SELECT = {
    "cs.AI": "Artificial Intelligence",
    "cs.LG": "Machine Learning",
    "cs.CL": "NLP",
    "cs.CV": "Computer Vision",
    "cs.RO": "Robotics",
}


class NotionClient:
    """Client for interacting with Notion API."""
    
    def __init__(
        self,
        api_key: str = None,
        database_id: str = None,
        parent_page_id: str = None,
    ):
        """
        Initialize the Notion client.
        
        Args:
            api_key: Notion integration token (defaults to NOTION_API_KEY env var)
            database_id: ID of the papers database (defaults to NOTION_DATABASE_ID env var)
            parent_page_id: ID of the parent page for daily summaries (defaults to NOTION_PARENT_PAGE_ID env var)
        """
        self.api_key = api_key or os.getenv("NOTION_API_KEY")
        if not self.api_key:
            raise ValueError("NOTION_API_KEY environment variable is required")
        
        self.database_id = database_id or os.getenv("NOTION_DATABASE_ID")
        self.parent_page_id = parent_page_id or os.getenv("NOTION_PARENT_PAGE_ID")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": NOTION_API_VERSION,
        }
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def add_paper_to_database(self, paper: AnalyzedPaper) -> Optional[str]:
        """
        Add an analyzed paper to the Notion database.
        
        Args:
            paper: The analyzed paper to add
            
        Returns:
            The page ID if successful, None otherwise
        """
        if not self.database_id:
            raise ValueError("NOTION_DATABASE_ID is required to add papers")
        
        # Check if paper already exists
        if self._paper_exists(paper.paper.arxiv_id):
            print(f"Paper {paper.paper.arxiv_id} already exists, skipping...")
            return None
        
        # Get category select value
        category = CATEGORY_TO_SELECT.get(
            paper.paper.primary_category,
            "Machine Learning"  # Default fallback
        )
        
        # Truncate text fields to Notion's limits (2000 chars for rich_text)
        summary = self._truncate(paper.summary, 2000)
        key_innovation = self._truncate(paper.key_innovation, 2000)
        implementation = self._truncate(paper.implementation_details, 2000)
        authors = self._truncate(", ".join(paper.paper.authors), 2000)
        
        # Build the request payload
        payload = {
            "parent": {"database_id": self.database_id},
            "properties": {
                "Title": {
                    "title": [{"text": {"content": self._truncate(paper.paper.title, 2000)}}]
                },
                "Authors": {
                    "rich_text": [{"text": {"content": authors}}]
                },
                "Category": {
                    "select": {"name": category}
                },
                "Date": {
                    "date": {"start": paper.paper.published.strftime("%Y-%m-%d")}
                },
                "Innovation Score": {
                    "number": paper.innovation_score
                },
                "Summary": {
                    "rich_text": [{"text": {"content": summary}}]
                },
                "Key Innovation": {
                    "rich_text": [{"text": {"content": key_innovation}}]
                },
                "Implementation Details": {
                    "rich_text": [{"text": {"content": implementation}}]
                },
                "arXiv Link": {
                    "url": paper.paper.arxiv_url
                },
                "PDF Link": {
                    "url": paper.paper.pdf_url
                },
                "arXiv ID": {
                    "rich_text": [{"text": {"content": paper.paper.arxiv_id}}]
                },
            }
        }
        
        response = requests.post(
            f"{NOTION_API_BASE}/pages",
            headers=self.headers,
            json=payload,
        )
        
        if response.status_code == 200:
            page_id = response.json().get("id")
            print(f"Added paper: {paper.paper.title[:50]}...")
            return page_id
        else:
            print(f"Error adding paper {paper.paper.arxiv_id}: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    
    def add_papers_to_database(self, papers: list[AnalyzedPaper]) -> list[str]:
        """
        Add multiple papers to the database.
        
        Args:
            papers: List of analyzed papers
            
        Returns:
            List of page IDs for successfully added papers
        """
        page_ids = []
        for paper in papers:
            try:
                page_id = self.add_paper_to_database(paper)
                if page_id:
                    page_ids.append(page_id)
            except Exception as e:
                print(f"Error adding paper {paper.paper.arxiv_id}: {e}")
                continue
        
        print(f"Added {len(page_ids)} papers to database")
        return page_ids
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
    )
    def create_daily_summary_page(
        self,
        date_str: str,
        summary_content: str,
        papers: list[AnalyzedPaper],
    ) -> Optional[str]:
        """
        Create a daily summary page.
        
        Args:
            date_str: Date string for the title (e.g., "2024-11-29")
            summary_content: Markdown content for the summary
            papers: List of analyzed papers to include
            
        Returns:
            The page ID if successful, None otherwise
        """
        if not self.parent_page_id:
            raise ValueError("NOTION_PARENT_PAGE_ID is required to create summary pages")
        
        # Build the page content
        content_blocks = self._markdown_to_blocks(summary_content)
        
        # Add a section with links to individual papers
        content_blocks.extend([
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "Papers Analyzed Today"}}]
                }
            },
            {
                "object": "block",
                "type": "divider",
                "divider": {}
            }
        ])
        
        # Add paper links as bullet points
        for paper in papers[:20]:  # Limit to avoid too long pages
            content_blocks.append({
                "object": "block",
                "type": "bulleted_list_item",
                "bulleted_list_item": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": f"[{paper.innovation_score}/10] ",
                            },
                            "annotations": {"bold": True}
                        },
                        {
                            "type": "text",
                            "text": {
                                "content": paper.paper.title[:80] + ("..." if len(paper.paper.title) > 80 else ""),
                                "link": {"url": paper.paper.arxiv_url}
                            }
                        }
                    ]
                }
            })
        
        # Create the page
        payload = {
            "parent": {"page_id": self.parent_page_id},
            "icon": {"type": "emoji", "emoji": "📚"},
            "properties": {
                "title": {
                    "title": [{"text": {"content": f"Daily Summary - {date_str}"}}]
                }
            },
            "children": content_blocks[:100]  # Notion API limit
        }
        
        response = requests.post(
            f"{NOTION_API_BASE}/pages",
            headers=self.headers,
            json=payload,
        )
        
        if response.status_code == 200:
            page_id = response.json().get("id")
            print(f"Created daily summary page for {date_str}")
            return page_id
        else:
            print(f"Error creating summary page: {response.status_code}")
            print(f"Response: {response.text}")
            return None
    
    def _paper_exists(self, arxiv_id: str) -> bool:
        """Check if a paper already exists in the database."""
        if not self.database_id:
            return False
        
        payload = {
            "filter": {
                "property": "arXiv ID",
                "rich_text": {"equals": arxiv_id}
            }
        }
        
        response = requests.post(
            f"{NOTION_API_BASE}/databases/{self.database_id}/query",
            headers=self.headers,
            json=payload,
        )
        
        if response.status_code == 200:
            results = response.json().get("results", [])
            return len(results) > 0
        
        return False
    
    def _truncate(self, text: str, max_length: int) -> str:
        """Truncate text to max length."""
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."
    
    def _markdown_to_blocks(self, markdown: str) -> list[dict]:
        """
        Convert markdown text to Notion blocks.
        This is a simplified converter that handles basic markdown.
        """
        blocks = []
        lines = markdown.split("\n")
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Skip empty lines
            if not line.strip():
                i += 1
                continue
            
            # Heading 1
            if line.startswith("# "):
                blocks.append({
                    "object": "block",
                    "type": "heading_1",
                    "heading_1": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                    }
                })
            
            # Heading 2
            elif line.startswith("## "):
                blocks.append({
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"type": "text", "text": {"content": line[3:].strip()}}]
                    }
                })
            
            # Heading 3
            elif line.startswith("### "):
                blocks.append({
                    "object": "block",
                    "type": "heading_3",
                    "heading_3": {
                        "rich_text": [{"type": "text", "text": {"content": line[4:].strip()}}]
                    }
                })
            
            # Bullet list
            elif line.startswith("- ") or line.startswith("* "):
                blocks.append({
                    "object": "block",
                    "type": "bulleted_list_item",
                    "bulleted_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                    }
                })
            
            # Numbered list
            elif len(line) > 2 and line[0].isdigit() and line[1] == ".":
                blocks.append({
                    "object": "block",
                    "type": "numbered_list_item",
                    "numbered_list_item": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                    }
                })
            
            # Divider
            elif line.strip() in ("---", "***", "___"):
                blocks.append({
                    "object": "block",
                    "type": "divider",
                    "divider": {}
                })
            
            # Quote
            elif line.startswith("> "):
                blocks.append({
                    "object": "block",
                    "type": "quote",
                    "quote": {
                        "rich_text": [{"type": "text", "text": {"content": line[2:].strip()}}]
                    }
                })
            
            # Regular paragraph
            else:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": line.strip()}}]
                    }
                })
            
            i += 1
        
        return blocks
    
    def get_database_info(self) -> Optional[dict]:
        """Get information about the papers database."""
        if not self.database_id:
            return None
        
        response = requests.get(
            f"{NOTION_API_BASE}/databases/{self.database_id}",
            headers=self.headers,
        )
        
        if response.status_code == 200:
            return response.json()
        return None


# For direct testing
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    client = NotionClient()
    
    # Test database connection
    db_info = client.get_database_info()
    if db_info:
        print(f"Connected to database: {db_info.get('title', [{}])[0].get('plain_text', 'Unknown')}")
    else:
        print("Could not connect to database. Make sure NOTION_DATABASE_ID is set.")

