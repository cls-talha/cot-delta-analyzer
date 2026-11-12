-- ==============================================================================
-- COT ANALYZER SUPABASE DATABASE SCHEMA
-- Run this in your Supabase SQL Editor (Supabase Dashboard -> SQL Editor -> New query)
-- ==============================================================================

-- 1. Commodity COT (Disaggregated Managed Money)
CREATE TABLE IF NOT EXISTS commodity_cot (
    report_date TEXT NOT NULL,
    commodity TEXT NOT NULL,
    long_pos NUMERIC,
    short_pos NUMERIC,
    spread NUMERIC,
    net_pos NUMERIC,
    long_pct DOUBLE PRECISION,
    short_pct DOUBLE PRECISION,
    open_interest NUMERIC,
    delta_net NUMERIC,
    delta_long NUMERIC,
    delta_short NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (report_date, commodity)
);

CREATE INDEX IF NOT EXISTS idx_commodity_cot_report_date ON commodity_cot(report_date);

-- 2. Current Week Overview
CREATE TABLE IF NOT EXISTS cot_current_week_overview (
    report_date TEXT NOT NULL,
    currency TEXT NOT NULL,
    lf_delta DOUBLE PRECISION,
    am_delta DOUBLE PRECISION,
    di_delta DOUBLE PRECISION,
    lf_am_long_positions NUMERIC,
    lf_am_short_positions NUMERIC,
    total_oi NUMERIC,
    delta_long_positions NUMERIC,
    delta_short_positions NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (report_date, currency)
);

CREATE INDEX IF NOT EXISTS idx_cot_overview_report_date ON cot_current_week_overview(report_date);

-- 3. Leveraged Funds Breakdown
CREATE TABLE IF NOT EXISTS cot_leveraged_funds_breakdown (
    report_date TEXT NOT NULL,
    currency TEXT NOT NULL,
    net_positions NUMERIC,
    net_percent DOUBLE PRECISION,
    net_percent_lf DOUBLE PRECISION,
    net_pct_lf_delta DOUBLE PRECISION,
    lf_long_delta NUMERIC,
    lf_short_delta NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (report_date, currency)
);

CREATE INDEX IF NOT EXISTS idx_cot_lf_breakdown_report_date ON cot_leveraged_funds_breakdown(report_date);

-- 4. COT Detailed Breakdown
CREATE TABLE IF NOT EXISTS cot_detailed_breakdown (
    report_date TEXT NOT NULL,
    currency TEXT NOT NULL,
    delta_total_oi NUMERIC,
    delta_lf_oi NUMERIC,
    delta_lf_longs_usd_b DOUBLE PRECISION,
    delta_lf_shorts_usd_b DOUBLE PRECISION,
    delta_am_longs_usd_b DOUBLE PRECISION,
    delta_am_shorts_usd_b DOUBLE PRECISION,
    am_long_delta NUMERIC,
    am_short_delta NUMERIC,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (report_date, currency)
);

CREATE INDEX IF NOT EXISTS idx_cot_detailed_breakdown_report_date ON cot_detailed_breakdown(report_date);

-- ==============================================================================
-- Auto-Enable Row Level Security (RLS) on all future tables
-- ==============================================================================

CREATE OR REPLACE FUNCTION enable_rls_on_new_table()
RETURNS event_trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    obj record;
BEGIN
    FOR obj IN SELECT * FROM pg_event_trigger_ddl_commands() 
               WHERE command_tag = 'CREATE TABLE' AND schema_name = 'public'
    LOOP
        EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY;', obj.schema_name, obj.name);
    END LOOP;
END;
$$;

DROP EVENT TRIGGER IF EXISTS trigger_enable_rls_on_new_table;

CREATE EVENT TRIGGER trigger_enable_rls_on_new_table
ON ddl_command_end
WHEN TAG IN ('CREATE TABLE')
EXECUTE FUNCTION enable_rls_on_new_table();

-- ==============================================================================
-- Row Level Security (RLS) Policies
-- ==============================================================================

ALTER TABLE commodity_cot ENABLE ROW LEVEL SECURITY;
ALTER TABLE cot_current_week_overview ENABLE ROW LEVEL SECURITY;
ALTER TABLE cot_leveraged_funds_breakdown ENABLE ROW LEVEL SECURITY;
ALTER TABLE cot_detailed_breakdown ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Allow public read access commodity_cot" ON commodity_cot FOR SELECT USING (true);
CREATE POLICY "Allow public write access commodity_cot" ON commodity_cot FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow public read access cot_current_week_overview" ON cot_current_week_overview FOR SELECT USING (true);
CREATE POLICY "Allow public write access cot_current_week_overview" ON cot_current_week_overview FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow public read access cot_leveraged_funds_breakdown" ON cot_leveraged_funds_breakdown FOR SELECT USING (true);
CREATE POLICY "Allow public write access cot_leveraged_funds_breakdown" ON cot_leveraged_funds_breakdown FOR ALL USING (true) WITH CHECK (true);

CREATE POLICY "Allow public read access cot_detailed_breakdown" ON cot_detailed_breakdown FOR SELECT USING (true);
CREATE POLICY "Allow public write access cot_detailed_breakdown" ON cot_detailed_breakdown FOR ALL USING (true) WITH CHECK (true);
