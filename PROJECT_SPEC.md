# Ethiopian Financial Intelligence Bureau (Backend Engine)
**Project Specification & Architecture Guide for Cursor / AI Agents**

## 1. Executive Summary & Objective
This project is an automated B2B Financial Intelligence engine covering the Ethiopian Capital Market ecosystem (ESX, ECMA, NBE, Tier-1 Issuers, and Commercial Media). 
The core objective is to ingest fragmented regulatory and financial news, resolve temporal inconsistencies (Ge'ez Ethiopian Calendar → ISO-8601 Gregorian), filter relevance via keyword signals, and pass enriched payloads into an LLM Analytical Core for structured market intelligence.

---

## 2. Tech Stack & Core Dependencies
- **Runtime:** Python 3.10+ (Asynchronous `asyncio`)
- **HTTP Client:** `httpx` (Asynchronous fetching, custom headers, SSL verification overrides)
- **HTML Parser:** `beautifulsoup4`
- **Date Conversion:** `py-ethiopian-date-converter`
- **LLM Structured Data:** `instructor` + `pydantic` + `openai` (or local Ollama API)
- **Persistence:** Local JSON / SQLite (fingerprinted via `hashlib` SHA-256)

---

## 3. Architecture & Modular Structure

Create the following file directory structure:

```text
ethio_fin_bureau/
├── config.py             # Target Feeds, Keywords, Constants
├── main.py               # Orchestrator & CLI Runner
├── middleware/
├──   ├── date_converter.py # Ge'ez to Gregorian Converter
├──   └── prefilter.py      # Keyword Filtering Logic
├── scrapers/
├──   └── ingestion.py      # Async Multi-Tier Scraper Engine
├── llm/
│   ├── schemas.py        # Pydantic Output Schemas
│   └── analyzer.py       # LLM Execution with Instructor
└── output.json           # Local Data Store (SHA-256 Deduplicated)