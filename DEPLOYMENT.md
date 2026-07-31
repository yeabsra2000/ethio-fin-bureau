# Deployment Guide - Ethiopian Financial Intelligence Bureau

## Production-Ready Deployment with Zero Cost

This guide covers deployment using free-tier services (GitHub Actions + Neon/Supabase PostgreSQL).

---

## 1. Environment Variables & Secrets

### Required Secrets for GitHub Actions

Configure these in your GitHub repository: **Settings → Secrets and variables → Actions → New repository secret**

#### A. LLM Configuration (Choose One)

**Option 1: OpenRouter (Recommended - Free Tier Available)**
```
Name: OPENROUTER_API_KEY
Value: sk-or-v1-... (Get from https://openrouter.ai/keys)
```

**Option 2: OpenAI**
```
Name: OPENAI_API_KEY
Value: sk-... (Get from https://platform.openai.com/api-keys)
```

#### B. Telegram Alerts

```
Name: TELEGRAM_BOT_TOKEN
Value: 123456789:ABCdefGhIJKlmNoPQRstUvWxYz123456 (From @BotFather)

Name: TELEGRAM_CHAT_ID
Value: 8947037161 (Your Telegram user/group ID)
```

**How to get Telegram credentials:**
1. Message @BotFather in Telegram → `/newbot` → follow prompts → copy token
2. Message your bot → visit `https://api.telegram.org/bot<TOKEN>/getUpdates` → find your chat ID

#### C. Database (Optional - For Production)

**Option 1: Neon PostgreSQL (Free Tier - Recommended)**
1. Sign up at https://neon.tech
2. Create a new project
3. Copy the connection string (looks like: `postgresql://user:pass@ep-xxx.region.aws.neon.tech/dbname`)
4. Add as secret:

```
Name: DATABASE_URL
Value: postgresql://user:pass@ep-xxx.region.aws.neon.tech/dbname
```

**Option 2: Supabase PostgreSQL (Free Tier)**
1. Sign up at https://supabase.com
2. Create a new project
3. Go to Settings → Database → Connection string
4. Copy the URI format connection string
5. Add as secret:

```
Name: DATABASE_URL
Value: postgresql://postgres:[password]@[host]:[port]/postgres
```

**Option 3: Local SQLite (Default - No configuration needed)**
- If `DATABASE_URL` is not set, the system automatically uses local SQLite
- Database file: `ethio_fin_bureau/data/bureau.db`

---

## 2. Local Development Setup

### Step 1: Clone Repository
```bash
git clone <your-repo-url>
cd ethio_fin_bureau
```

### Step 2: Create Virtual Environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### Step 3: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment
```bash
# Copy example env file
cp .env.example .env  # If you have one, or create .env manually

# Edit .env with your credentials
notepad .env  # Windows
nano .env     # Mac/Linux
```

**Minimum .env configuration:**
```env
# Required for LLM analysis
OPENROUTER_API_KEY=sk-or-v1-...

# Required for Telegram alerts
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_CHAT_ID=8947037161

# Optional: PostgreSQL (leave empty for local SQLite)
DATABASE_URL=postgresql://...

# Optional: Use SQLite (default: True)
USE_SQLITE=True
```

### Step 5: Test Locally
```bash
# Test scraping + LLM + database
python -m ethio_fin_bureau.main --llm --new-schema --llm-max 3 --db

# Test with Telegram alerts
python -m ethio_fin_bureau.main --llm --new-schema --llm-max 3 --db --telegram

# Check database stats
python -m ethio_fin_bureau.main --stats
```

---

## 3. GitHub Actions Deployment

### Step 1: Push to GitHub
```bash
git add .
git commit -m "Initial production deployment"
git push origin main
```

### Step 2: Configure Secrets
1. Go to your GitHub repository
2. **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret from Section 1 above

### Step 3: Enable Workflow
The workflow file `.github/workflows/scraper.yml` is already configured.

**Schedule:** Runs automatically Monday-Friday, 9 AM - 5 PM Ethiopian time (UTC+3)

**Manual Trigger:**
1. Go to **Actions** tab
2. Select "Financial Intelligence Scraper"
3. Click **Run workflow** → **Run workflow**

### Step 4: Monitor Runs
- View logs: **Actions** → Select workflow run
- Download artifacts: Output JSON and database files
- Failure alerts: Sent to your Telegram chat

---

## 4. Production Features

### ✅ No Duplicate Sending
- **SHA-256 content hashing** prevents duplicate records
- Database checks before saving
- Idempotent pipeline (safe to run multiple times)

### ✅ Zero-Cost Hosting
- **GitHub Actions:** 2,000 free minutes/month (sufficient for hourly runs)
- **Neon PostgreSQL:** 512 MB free storage (permanent)
- **Supabase PostgreSQL:** 500 MB free storage (permanent)

### ✅ Automatic Scheduling
- Runs during Ethiopian market hours (Mon-Fri, 9 AM - 5 PM EAT)
- No server required - serverless execution
- Automatic retries on failure

### ✅ Production Monitoring
- Telegram alerts for HIGH/MEDIUM impact intelligence
- Failure notifications via Telegram
- Artifact retention (30 days) for debugging

---

## 5. Database Schema

### SQLite (Local Development)
```
File: ethio_fin_bureau/data/bureau.db
Tables: financial_records
```

### PostgreSQL (Production)
```
Host: Provided by Neon/Supabase
Database: bureau
Tables: financial_records
Connection pooling: 5 connections, 10 overflow
```

### Schema Details
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
    affected_entities TEXT,        -- JSON array
    trading_implication TEXT,
    event_type VARCHAR(50),        -- NEW: regulatory, listing, monetary_policy, etc.
    time_horizon VARCHAR(20),      -- NEW: immediate, short_term, medium_term, long_term
    confidence_score FLOAT,        -- NEW: 0.0-1.0 confidence in assessment
    key_metrics TEXT,              -- NEW: JSON array of {name, value, context}
    actionable_signals TEXT,       -- NEW: JSON array of {signal_type, asset, rationale, urgency}
    synthesized_market_impact TEXT, -- NEW: combined impact from historical context
    historical_connections TEXT,    -- NEW: JSON array of related past events
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE UNIQUE INDEX idx_content_hash ON financial_records(content_hash);
CREATE INDEX idx_financial_records_event_type ON financial_records(event_type);
CREATE INDEX idx_financial_records_impact_level ON financial_records(impact_level);
CREATE INDEX idx_financial_records_sentiment ON financial_records(sentiment);
```

### Migration for Existing Databases
If you already have a database, run this migration to add the new columns:
```sql
-- See migrate_add_new_columns.sql for the full migration
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS event_type VARCHAR(50);
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS time_horizon VARCHAR(20);
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS confidence_score FLOAT;
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS key_metrics TEXT;
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS actionable_signals TEXT;
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS synthesized_market_impact TEXT;
ALTER TABLE financial_records ADD COLUMN IF NOT EXISTS historical_connections TEXT;
```

---

## 6. Troubleshooting

### Issue: "No module named 'psycopg2'"
**Solution:** Install PostgreSQL driver
```bash
pip install psycopg2-binary
```

### Issue: "Database connection failed"
**Solution:** Check DATABASE_URL format
```bash
# Correct format:
postgresql://user:password@host:port/dbname

# NOT:
postgres://user:password@host:port/dbname  # Old format
```

### Issue: "Telegram 403 Forbidden"
**Solution:** 
1. Verify bot token from @BotFather
2. Ensure you messaged your bot at least once
3. Get correct chat ID from `https://api.telegram.org/bot<TOKEN>/getUpdates`

### Issue: "GitHub Actions not triggering"
**Solution:**
1. Check workflow file is in `.github/workflows/`
2. Verify secrets are configured
3. Check Actions tab for error logs

### Issue: "Duplicate records in database"
**Solution:** This shouldn't happen! If it does:
1. Check `content_hash` is being generated correctly
2. Verify `is_hash_exists()` is called before `save_record()`
3. Check database indexes are created

---

## 7. Cost Breakdown

### Free Tier (Recommended for Starting)
| Service | Free Limit | Your Usage | Cost |
|---------|-----------|------------|------|
| GitHub Actions | 2,000 min/month | ~135 min/month (9 runs × 15 min) | $0 |
| Neon PostgreSQL | 512 MB storage | ~10 MB/year | $0 |
| OpenRouter API | Free models | ~9,000 tokens/day | $0 |
| Telegram API | Unlimited | ~100 messages/day | $0 |
| **TOTAL** | | | **$0/month** |

### Paid Tier (If You Need More)
| Service | Cost | When to Upgrade |
|---------|------|-----------------|
| GitHub Actions | $0.008/min | >2,000 min/month |
| Neon PostgreSQL | $19/month | >512 MB storage |
| OpenRouter API | Pay-per-token | Need premium models |
| **TOTAL** | ~$19-50/month | High-volume production |

---

## 8. Security Best Practices

### ✅ DO:
- Store secrets in GitHub Secrets (encrypted)
- Use environment variables (never hardcode)
- Enable 2FA on GitHub and Telegram
- Use strong, unique passwords for databases
- Rotate API keys periodically

### ❌ DON'T:
- Commit `.env` file to git
- Share bot tokens or API keys
- Use `@gmail.com` for production bots
- Expose database credentials in logs
- Run pipeline as root/admin

---

## 9. Monitoring & Maintenance

### Daily Checks
- [ ] Verify Telegram alerts received
- [ ] Check GitHub Actions run status
- [ ] Monitor database size (should grow slowly)

### Weekly Checks
- [ ] Review intelligence reports quality
- [ ] Check for false positives/negatives
- [ ] Verify all sources scraping correctly

### Monthly Checks
- [ ] Rotate API keys (security best practice)
- [ ] Review GitHub Actions minutes usage
- [ ] Check database storage usage
- [ ] Update dependencies (`pip install --upgrade`)

---

## 10. Support & Documentation

### Project Documentation
- `README.md` - Project overview
- `PROJECT_SPEC.md` - Technical architecture
- `DEPLOYMENT.md` - This file

### External Resources
- [OpenRouter Docs](https://openrouter.ai/docs)
- [Telegram Bot API](https://core.telegram.org/bots/api)
- [Neon PostgreSQL](https://neon.tech/docs)
- [GitHub Actions](https://docs.github.com/en/actions)

### Getting Help
1. Check GitHub Issues
2. Review workflow logs in Actions tab
3. Test locally before deploying
4. Verify all secrets are configured

---

## Quick Start Checklist

- [ ] Fork/clone repository
- [ ] Create `.env` with local credentials
- [ ] Test pipeline locally (`python -m ethio_fin_bureau.main --llm --new-schema --llm-max 3 --db --telegram`)
- [ ] Push to GitHub
- [ ] Configure GitHub Secrets (OPENROUTER_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, DATABASE_URL)
- [ ] Enable GitHub Actions workflow
- [ ] Verify first automated run succeeds
- [ ] Check Telegram for alerts
- [ ] Monitor database growth

**You're now production-ready! 🚀**