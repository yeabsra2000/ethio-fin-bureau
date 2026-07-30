# 🇪🇹 Ethiopian Financial Intelligence Bureau

**Automated B2B Financial Intelligence Engine for the Ethiopian Capital Market Ecosystem**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![GitHub Actions](https://img.shields.io/badge/github%20actions-enabled-brightgreen)](https://github.com/features/actions)

An automated financial intelligence system that monitors Ethiopian capital market sources (ESX, ECMA, NBE, commercial media), analyzes news using LLMs, and delivers actionable intelligence via Telegram alerts.

## ✨ Features

- **🔍 Automated Scraping** - Monitors 8+ financial sources every hour during market hours
- **🤖 LLM Analysis** - AI-powered sentiment analysis and impact assessment
- **💾 Smart Persistence** - SQLite (local) or PostgreSQL (production) with SHA-256 deduplication
- **📱 Telegram Alerts** - Real-time notifications for HIGH/MEDIUM impact intelligence
- **⏰ Scheduled Runs** - Automated execution during Ethiopian market hours (Mon-Fri, 9 AM - 5 PM EAT)
- **🔄 Zero Duplicates** - Content-hash-based deduplication prevents duplicate records
- **💰 Zero Cost** - Deploys on free-tier services (GitHub Actions + Neon PostgreSQL)
- **📊 Production Ready** - Comprehensive logging, error handling, and monitoring

## 🏗️ Architecture

```
┌─────────────────┐
│  GitHub Actions │  (Hourly cron during market hours)
│  Scheduler      │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│         Financial Intelligence Engine        │
├─────────────────────────────────────────────┤
│ 1. Scraping Layer (httpx + BeautifulSoup)   │
│    - ESX, ECMA, NBE, EthioTelecom, etc.    │
│                                             │
│ 2. Middleware Layer                         │
│    - Date conversion (Ge'ez → Gregorian)   │
│    - Keyword filtering & relevance scoring  │
│                                             │
│ 3. LLM Analysis Layer (OpenRouter/OpenAI)  │
│    - Sentiment analysis                     │
│    - Impact assessment                      │
│    - Entity extraction                      │
│                                             │
│ 4. Persistence Layer                        │
│    - SHA-256 content hashing                │
│    - SQLite (dev) / PostgreSQL (prod)       │
│    - Deduplication                          │
│                                             │
│ 5. Delivery Layer                           │
│    - Telegram alerts (HIGH/MEDIUM impact)   │
│    - Failure notifications                  │
└─────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Git
- Telegram account (for alerts)

### Installation

```bash
# Clone repository
git clone <your-repo-url>
cd ethio_fin_bureau

# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your API keys
notepad .env  # Windows
nano .env     # Mac/Linux
```

### Configuration

Edit `.env` with your credentials:

```env
# Required: LLM API Key (OpenRouter recommended - free tier)
OPENROUTER_API_KEY=sk-or-v1-your-key-here

# Required: Telegram Bot (get from @BotFather)
TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRstUvWxYz123456
TELEGRAM_CHAT_ID=8947037161

# Optional: PostgreSQL (leave empty for local SQLite)
# DATABASE_URL=postgresql://user:pass@host:port/dbname
```

### Run Locally

```bash
# Basic pipeline (scraping + filtering)
python -m ethio_fin_bureau.main

# With LLM analysis
python -m ethio_fin_bureau.main --llm --new-schema --llm-max 3

# With database persistence
python -m ethio_fin_bureau.main --llm --new-schema --llm-max 3 --db

# With Telegram alerts
python -m ethio_fin_bureau.main --llm --new-schema --llm-max 3 --db --telegram

# Check database statistics
python -m ethio_fin_bureau.main --stats
```

## 📦 Production Deployment (Zero Cost)

Deploy automatically using GitHub Actions + free-tier PostgreSQL.

### Step 1: Push to GitHub

```bash
git add .
git commit -m "Initial production deployment"
git push origin main
```

### Step 2: Configure GitHub Secrets

Go to: **Repository → Settings → Secrets and variables → Actions**

Add these secrets:

| Secret | Value | How to Get |
|--------|-------|------------|
| `OPENROUTER_API_KEY` | `sk-or-v1-...` | https://openrouter.ai/keys |
| `TELEGRAM_BOT_TOKEN` | `123456789:ABC...` | Message @BotFather → `/newbot` |
| `TELEGRAM_CHAT_ID` | `8947037161` | Message bot → https://api.telegram.org/bot<TOKEN>/getUpdates |
| `DATABASE_URL` | `postgresql://...` | https://neon.tech (free tier) |

### Step 3: Enable Workflow

The workflow `.github/workflows/scraper.yml` is pre-configured.

**Schedule:** Runs Monday-Friday, 9 AM - 5 PM Ethiopian time (UTC+3)

**Manual Trigger:**
1. Go to **Actions** tab
2. Select "Financial Intelligence Scraper"
3. Click **Run workflow**

### Step 4: Monitor

- **View logs:** Actions → Select workflow run
- **Download artifacts:** Output JSON + database files
- **Telegram alerts:** Receive HIGH/MEDIUM impact intelligence
- **Failure notifications:** Sent to your Telegram chat

## 🗄️ Database

### SQLite (Local Development)

- **Location:** `ethio_fin_bureau/data/bureau.db`
- **No configuration needed**
- **Best for:** Local testing

### PostgreSQL (Production)

**Recommended Providers:**
- [Neon](https://neon.tech) - 512 MB free
- [Supabase](https://supabase.com) - 500 MB free

**Connection:**
```bash
# Set DATABASE_URL environment variable
export DATABASE_URL=postgresql://user:pass@host:port/dbname
```

**Schema:**
```sql
CREATE TABLE financial_records (
    id SERIAL PRIMARY KEY,
    content_hash VARCHAR(64) UNIQUE NOT NULL,
    source_name VARCHAR(100) NOT NULL,
    tier VARCHAR(50) NOT NULL,
    headline VARCHAR(500) NOT NULL,
    url VARCHAR(1000) NOT NULL,
    normalized_date VARCHAR(20),
    executive_summary TEXT,
    sentiment VARCHAR(20),
    impact_level VARCHAR(20),
    primary_asset_class VARCHAR(50),
    affected_entities TEXT,
    trading_implication TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_content_hash ON financial_records(content_hash);
```

## 📊 Data Sources

### Tier 1: Regulatory Bodies
- **ESX** - Ethiopian Securities Exchange
- **ECMA** - Ethiopian Capital Market Authority
- **NBE** - National Bank of Ethiopia

### Tier 2: Financial Media
- **Capital Ethiopia** - Business news
- **The Reporter Ethiopia** - Investigative journalism

### Tier 3: Issuer IR Pages
- **EthioTelecom** - Investor relations
- **Awash Bank** - Corporate news

## 🔧 CLI Commands

```bash
# Run full pipeline
python -m ethio_fin_bureau.main --llm --new-schema --llm-max 10 --db --telegram

# Scrape only (no LLM)
python -m ethio_fin_bureau.main

# LLM analysis only
python -m ethio_fin_bureau.main --llm --llm-max 5

# Database statistics
python -m ethio_fin_bureau.main --stats

# Help
python -m ethio_fin_bureau.main --help
```

## 📈 Output Format

### JSON Output (`output.json`)

```json
{
  "scraped_at": "2026-07-30T11:25:15+00:00",
  "total_items": 76,
  "articles": [...],
  "intelligence": [
    {
      "headline": "NIB Insurance registers securities with ECMA",
      "sentiment": "BULLISH",
      "impact_level": "HIGH",
      "primary_asset_class": "INSURANCE",
      "affected_entities": ["NIB Insurance", "ECMA"],
      "executive_summary": "Full summary...",
      "trading_implication": "Trading implication...",
      "confidence_score": 0.95
    }
  ]
}
```

### Telegram Alert

```
📊 Financial Intelligence Alert

Headline: NIB Insurance registers securities with ECMA

Source: ECMA_NEWS
Date: 2026-07-30
Sentiment: BULLISH
Impact Level: HIGH
Asset Class: INSURANCE

Executive Summary:
NIB Insurance S.C.'s securities registration with ECMA signals potential entry into capital markets...

Trading Implication:
Consider monitoring NIB Insurance for upcoming IPO...

Ethiopian Financial Intelligence Bureau
```

## 🛡️ Production Features

### ✅ No Duplicate Sending
- SHA-256 content hashing
- Database uniqueness constraints
- Idempotent pipeline execution

### ✅ Automatic Scheduling
- Runs during Ethiopian market hours (Mon-Fri, 9 AM - 5 PM EAT)
- No server required (serverless)
- Automatic retries on failure

### ✅ Monitoring & Alerts
- Telegram notifications for HIGH/MEDIUM impact
- Failure alerts sent to your chat
- 30-day artifact retention for debugging

## 🔒 Security

### Best Practices
- ✅ Store secrets in GitHub Secrets (encrypted)
- ✅ Use environment variables (never hardcode)
- ✅ Enable 2FA on GitHub and Telegram
- ✅ Use strong database passwords
- ✅ Rotate API keys monthly

### What NOT to Do
- ❌ Commit `.env` to git
- ❌ Share bot tokens or API keys
- ❌ Expose credentials in logs
- ❌ Run as root/admin

## 🐛 Troubleshooting

### "No module named 'psycopg2'"
```bash
pip install psycopg2-binary
```

### "Database connection failed"
```bash
# Check DATABASE_URL format
postgresql://user:password@host:port/dbname
# NOT: postgres://... (old format)
```

### "Telegram 403 Forbidden"
1. Verify bot token from @BotFather
2. Message your bot at least once
3. Get correct chat ID from getUpdates

### "GitHub Actions not triggering"
1. Check workflow is in `.github/workflows/`
2. Verify secrets are configured
3. Check Actions tab for errors

## 📝 Project Structure

```
ethio_fin_bureau/
├── config.py                    # Configuration & constants
├── main.py                      # CLI orchestrator
├── output.json                  # Latest output
├── pipeline.log                 # Application logs
├── data/
│   └── bureau.db               # SQLite database (local)
├── db/
│   ├── __init__.py
│   ├── models.py               # SQLAlchemy models
│   └── database.py             # Database operations
├── delivery/
│   ├── __init__.py
│   └── telegram.py             # Telegram alerts
├── llm/
│   ├── schemas.py              # Pydantic models
│   └── analyzer.py             # LLM execution
├── middleware/
│   ├── date_converter.py       # Ge'ez → Gregorian
│   └── prefilter.py            # Keyword filtering
└── scrapers/
    └── ingestion.py            # Async scraper engine

.github/
└── workflows/
    └── scraper.yml             # GitHub Actions schedule

DEPLOYMENT.md                   # Deployment guide
README.md                       # This file
requirements.txt                # Python dependencies
.env.example                    # Environment template
.gitignore                      # Git ignore rules
```

## 📚 Documentation

- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Complete deployment guide
- **[PROJECT_SPEC.md](PROJECT_SPEC.md)** - Technical architecture
- **[.env.example](.env.example)** - Configuration template

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## 📄 License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [OpenRouter](https://openrouter.ai) - Free LLM API access
- [Neon](https://neon.tech) - Free PostgreSQL hosting
- [GitHub Actions](https://github.com/features/actions) - Free CI/CD
- Ethiopian Capital Market Authority - Market data

## 📞 Support

- **Issues:** [GitHub Issues](https://github.com/yourusername/ethio-fin-bureau/issues)
- **Documentation:** See [DEPLOYMENT.md](DEPLOYMENT.md)
- **Telegram:** @EthioFinBureauSupport

---

**Built with ❤️ for the Ethiopian Financial Community**

**Status:** ✅ Production Ready | 🚀 Deployed | 📱 Alerts Active
