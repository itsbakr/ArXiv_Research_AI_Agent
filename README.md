# ArXiv AI Research Agent

An automated AI agent that monitors arXiv for the latest research papers in AI, Machine Learning, NLP, Computer Vision, and Robotics. It uses Claude to identify and summarize the most innovative papers, storing results in a Notion database with daily summary pages.

## Features

- **Multi-category monitoring**: Tracks cs.AI, cs.LG, cs.CL, cs.CV, and cs.RO
- **AI-powered analysis**: Uses Claude to rank papers by innovation and generate detailed summaries
- **Notion integration**: Creates a searchable database of papers + daily summary pages
- **Automated scheduling**: Runs every weekday via GitHub Actions

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  GitHub Actions │────▶│  Python Agent    │────▶│     Notion      │
│  (Weekday Cron) │     │  + Claude API    │     │  (Database +    │
└─────────────────┘     └──────────────────┘     │   Daily Pages)  │
                               │                 └─────────────────┘
                               ▼
                        ┌──────────────────┐
                        │   arXiv API      │
                        │   (5 categories) │
                        └──────────────────┘
```

## Setup

### 1. Install Dependencies

```bash
cd arxiv-agent
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Required variables:
- `ANTHROPIC_API_KEY`: Your Anthropic API key from https://console.anthropic.com/
- `NOTION_API_KEY`: Your Notion integration token from https://www.notion.so/my-integrations
- `NOTION_PARENT_PAGE_ID`: The ID of a Notion page shared with your integration

### 3. Create Notion Integration

1. Go to https://www.notion.so/my-integrations
2. Create a new integration
3. Copy the "Internal Integration Token"
4. Create a page in Notion where you want the database
5. Share that page with your integration (click "..." → "Connections" → select your integration)
6. Copy the page ID from the URL

### 4. Run Locally

```bash
python -m src.main
```

### 5. GitHub Actions (Automated)

The agent runs automatically every weekday at 8 AM UTC. To enable:

1. Push this repo to GitHub
2. Add secrets in Settings → Secrets → Actions:
   - `ANTHROPIC_API_KEY`
   - `NOTION_API_KEY`
   - `NOTION_PARENT_PAGE_ID`

## Project Structure

```
arxiv-agent/
├── src/
│   ├── __init__.py
│   ├── arxiv_fetcher.py    # Fetch papers from arXiv API
│   ├── paper_analyzer.py   # Claude-based analysis & ranking
│   ├── notion_client.py    # Notion database & page operations
│   └── main.py             # Orchestration entry point
├── .github/
│   └── workflows/
│       └── daily_arxiv.yml # Weekday cron schedule
├── requirements.txt
├── .env.example
└── README.md
```

## Notion Database Schema

The agent creates a database with the following fields:

| Field | Type | Description |
|-------|------|-------------|
| Title | Title | Paper title |
| Authors | Text | Paper authors |
| Category | Select | AI/ML/NLP/CV/Robotics |
| Date | Date | Submission date |
| Innovation Score | Number | 1-10 rating by Claude |
| Summary | Text | Executive summary |
| Key Innovation | Text | Main contribution |
| Implementation Details | Text | Technical approach |
| arXiv Link | URL | Link to abstract |
| PDF Link | URL | Direct PDF link |

## Daily Summary Pages

Each day creates a new page under the parent containing:
- Executive summary of the day's most interesting papers
- Categorized highlights by research area
- Links to individual paper entries in the database
