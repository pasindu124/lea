CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ------------------------------------------------------------------ data tables
CREATE TABLE IF NOT EXISTS parts_stock (
    id BIGSERIAL PRIMARY KEY,
    source_row INT NOT NULL,                 -- Excel row number in Inventory_List.xlsx
    store TEXT, location TEXT, part_no TEXT, serial TEXT, description TEXT,
    mat_class TEXT, qty NUMERIC, cond TEXT, order_no TEXT, rec_date DATE,
    owner TEXT, entity TEXT,
    search_text TEXT GENERATED ALWAYS AS (upper(
        coalesce(part_no,'')||' '||coalesce(serial,'')||' '||coalesce(description,'')||' '||coalesce(location,''))) STORED,
    search_norm TEXT GENERATED ALWAYS AS (regexp_replace(upper(
        coalesce(part_no,'')||' '||coalesce(serial,'')||' '||coalesce(description,'')||' '||coalesce(location,'')),
        '[^A-Z0-9]','','g')) STORED
);
CREATE INDEX IF NOT EXISTS parts_search_text_trgm ON parts_stock USING gin (search_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS parts_search_norm_trgm ON parts_stock USING gin (search_norm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS parts_part_no ON parts_stock (part_no);

CREATE TABLE IF NOT EXISTS tools (
    id BIGSERIAL PRIMARY KEY,
    source_file TEXT NOT NULL, source_row INT NOT NULL,
    part_no TEXT, serial TEXT, description TEXT, tool_id TEXT, mc TEXT, co TEXT,
    received DATE, expires DATE, partly_rec BOOLEAN, station TEXT, store TEXT,
    location TEXT, workload TEXT, qty NUMERIC,
    search_text TEXT GENERATED ALWAYS AS (upper(
        coalesce(part_no,'')||' '||coalesce(serial,'')||' '||coalesce(description,'')||' '||coalesce(location,''))) STORED,
    search_norm TEXT GENERATED ALWAYS AS (regexp_replace(upper(
        coalesce(part_no,'')||' '||coalesce(serial,'')||' '||coalesce(description,'')||' '||coalesce(location,'')),
        '[^A-Z0-9]','','g')) STORED
);
CREATE INDEX IF NOT EXISTS tools_search_text_trgm ON tools USING gin (search_text gin_trgm_ops);
CREATE INDEX IF NOT EXISTS tools_search_norm_trgm ON tools USING gin (search_norm gin_trgm_ops);

CREATE TABLE IF NOT EXISTS work_orders (
    id BIGSERIAL PRIMARY KEY,
    source_row INT NOT NULL,                 -- Excel row number in Maintenance_History.xlsx
    wo_number BIGINT, aircraft_reg TEXT, operator_code TEXT, wo_type TEXT,
    date_opened DATE, date_closed DATE, ata TEXT,
    wo_description TEXT, wo_actions TEXT, wo_state TEXT
);
CREATE INDEX IF NOT EXISTS wo_aircraft_state ON work_orders (aircraft_reg, wo_state);
CREATE INDEX IF NOT EXISTS wo_number_idx ON work_orders (wo_number);

CREATE TABLE IF NOT EXISTS aviatar_faults (
    id BIGSERIAL PRIMARY KEY,
    prio TEXT, msg_code NUMERIC, message TEXT, message_type TEXT, ac_type TEXT,
    ac TEXT, flight TEXT, phase INT, ata TEXT, source TEXT, occurrence TIMESTAMP,
    repetitive BOOLEAN, multiple BOOLEAN, source_file TEXT
);
CREATE INDEX IF NOT EXISTS aviatar_ac_time ON aviatar_faults (ac, occurrence);

CREATE TABLE IF NOT EXISTS pha_cases (
    id BIGSERIAL PRIMARY KEY,
    source_row INT NOT NULL,                 -- CSV data row number in the PHA export
    max_severity TEXT, acreg TEXT, ata INT, use_case TEXT, title TEXT, system TEXT,
    case_type TEXT, remarks INT, classification TEXT, impact TEXT,
    opened TIMESTAMP, updated TIMESTAMP, status TEXT, case_link TEXT
);
CREATE INDEX IF NOT EXISTS pha_acreg ON pha_cases (acreg, status);

-- ----------------------------------------------- app tables (survive data reloads)
CREATE TABLE IF NOT EXISTS audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    sources JSONB NOT NULL DEFAULT '[]'::jsonb
);
CREATE INDEX IF NOT EXISTS audit_ts ON audit_log (ts DESC);

CREATE TABLE IF NOT EXISTS roster (
    shift_date DATE NOT NULL,
    aircraft_reg TEXT NOT NULL,
    engineer TEXT NOT NULL,
    PRIMARY KEY (shift_date, aircraft_reg)
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

-- ------------------------------------------------------------------ AMM (maintenance manual) reference data
CREATE TABLE IF NOT EXISTS amm_tasks (
    task_no TEXT PRIMARY KEY,                -- 26-23-41-000-004-A (configuration letter last)
    base_task TEXT NOT NULL,                 -- 26-23-41-000-004
    title TEXT, ata TEXT, function_code TEXT, function_label TEXT, config TEXT, rev_date TEXT,
    fins TEXT[], zones TEXT[], identical_task_note TEXT, source_file TEXT
);
CREATE INDEX IF NOT EXISTS amm_tasks_base ON amm_tasks (base_task);
CREATE TABLE IF NOT EXISTS amm_task_items (
    id BIGSERIAL PRIMARY KEY,
    task_no TEXT NOT NULL REFERENCES amm_tasks (task_no) ON DELETE CASCADE,
    pos INT NOT NULL, kind TEXT NOT NULL,    -- tool | consumable | part | reference
    ref TEXT, qty TEXT, designation TEXT, extra TEXT
);
CREATE INDEX IF NOT EXISTS amm_items_task ON amm_task_items (task_no, pos);
CREATE TABLE IF NOT EXISTS amm_task_notes (
    id BIGSERIAL PRIMARY KEY,
    task_no TEXT NOT NULL REFERENCES amm_tasks (task_no) ON DELETE CASCADE,
    pos INT NOT NULL, kind TEXT NOT NULL, code TEXT, text TEXT
);
CREATE INDEX IF NOT EXISTS amm_notes_task ON amm_task_notes (task_no, pos);
