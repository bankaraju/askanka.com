-- OPUS ANKA — PostgreSQL Schemas
-- V2 Forensics (Port 5000) + V3 Trading (Port 9001)

-- ══════════════════════════════════════════════════════════════
-- V2 FORENSICS DATABASE
-- ══════════════════════════════════════════════════════════════

-- Unified XBRL financial data from BSE/NSE filings
CREATE TABLE IF NOT EXISTS xbrl_unified_data (
    id SERIAL PRIMARY KEY,
    company_cin VARCHAR(25),
    bse_scrip VARCHAR(10),
    nse_symbol VARCHAR(20),
    filing_type VARCHAR(20),        -- 'annual' | 'quarterly'
    period VARCHAR(10),             -- 'Q3FY25' | 'FY2024'
    filing_date DATE,
    source VARCHAR(10),             -- 'BSE' | 'NSE'
    format VARCHAR(10),             -- 'XBRL' | 'PDF_OCR'
    data JSONB NOT NULL,            -- Structured financial line items
    source_url TEXT,
    source_hash VARCHAR(64),        -- SHA256 of source document
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(bse_scrip, period, filing_type)
);

-- OCR extractions from PDF annual reports
CREATE TABLE IF NOT EXISTS document_extractions (
    id SERIAL PRIMARY KEY,
    company_cin VARCHAR(25),
    document_type VARCHAR(30),      -- 'annual_report' | 'transcript' | 'notice'
    document_year VARCHAR(10),
    page_number INT,
    extracted_text TEXT,
    extraction_method VARCHAR(20),  -- 'azure_ocr' | 'xbrl_parse'
    confidence FLOAT,
    source_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Discovered patterns from the Pattern Premium engine
CREATE TABLE IF NOT EXISTS discovered_patterns (
    id SERIAL PRIMARY KEY,
    pattern_type VARCHAR(30),       -- 'promise_delivery' | 'dropped_theme' | 'forensic_flag'
    company_cin VARCHAR(25),
    nse_symbol VARCHAR(20),
    description TEXT NOT NULL,
    severity VARCHAR(10),           -- 'INFO' | 'WARNING' | 'CRITICAL'
    evidence JSONB,                 -- Source references
    first_detected DATE,
    last_confirmed DATE,
    status VARCHAR(15) DEFAULT 'active',  -- 'active' | 'resolved' | 'stale'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Pattern instances — individual occurrences tied to specific filings
CREATE TABLE IF NOT EXISTS pattern_instances (
    id SERIAL PRIMARY KEY,
    pattern_id INT REFERENCES discovered_patterns(id),
    quarter VARCHAR(10),
    claim_text TEXT,
    target_value VARCHAR(50),
    actual_value VARCHAR(50),
    delivery_status VARCHAR(20),    -- 'delivered' | 'partially' | 'missed' | 'quietly_dropped'
    gap_pct FLOAT,
    source_filing_id INT REFERENCES xbrl_unified_data(id),
    source_page VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Source reliability rankings (compounding asset)
CREATE TABLE IF NOT EXISTS source_reliability (
    id SERIAL PRIMARY KEY,
    source_name VARCHAR(50),        -- 'BSE_XBRL' | 'NSE_PDF' | 'Screener' | 'Yahoo'
    entity_type VARCHAR(20),        -- 'financial' | 'pricing' | 'ownership'
    reliability_score FLOAT,        -- 0.0 to 1.0
    discrepancy_count INT DEFAULT 0,
    last_validated DATE,
    notes TEXT,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Management claims (raw extraction from Step 9)
CREATE TABLE IF NOT EXISTS management_claims (
    id SERIAL PRIMARY KEY,
    company_cin VARCHAR(25),
    nse_symbol VARCHAR(20),
    quarter VARCHAR(10),
    source_type VARCHAR(20),        -- 'annual_report' | 'transcript'
    source_page VARCHAR(20),
    claim_text TEXT NOT NULL,
    category VARCHAR(30),
    target_metric VARCHAR(50),
    target_value VARCHAR(50),
    target_timeline VARCHAR(20),
    extraction_confidence FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_xbrl_symbol ON xbrl_unified_data(nse_symbol, period);
CREATE INDEX IF NOT EXISTS idx_patterns_symbol ON discovered_patterns(nse_symbol);
CREATE INDEX IF NOT EXISTS idx_claims_symbol ON management_claims(nse_symbol, quarter);


-- ══════════════════════════════════════════════════════════════
-- V3 TRADING DATABASE (shares port 9001 with existing Anka V3)
-- ══════════════════════════════════════════════════════════════

-- Pattern Premium scores (output of Step 11)
CREATE TABLE IF NOT EXISTS pattern_premium_scores (
    id SERIAL PRIMARY KEY,
    nse_symbol VARCHAR(20),
    computed_date DATE,
    execution_score FLOAT,
    theme_diversity FLOAT,
    dropped_penalty FLOAT,
    digital_bonus FLOAT,
    final_premium FLOAT,
    valuation_applicable BOOLEAN DEFAULT TRUE,
    forensic_flags JSONB,
    report_path TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(nse_symbol, computed_date)
);
