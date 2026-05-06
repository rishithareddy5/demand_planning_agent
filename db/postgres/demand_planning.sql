-- =============================================================
-- DEMAND PLANNING AGENT — PostgreSQL Schema
-- db/demand_planning.sql
-- =============================================================

-- -------------------------------------------------------------
-- EXTENSIONS
-- -------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";


-- =============================================================
-- 1. DISTRIBUTORS
-- Master table of all distributors in the system.
-- distributor_code is the business ID like D01, D02, D03
-- =============================================================
CREATE TABLE IF NOT EXISTS distributors (
    distributor_id      UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_code    VARCHAR(50)     NOT NULL UNIQUE,
    name                VARCHAR(255)    NOT NULL,
    email               VARCHAR(255)    NOT NULL UNIQUE,
    phone               VARCHAR(30),
    region              VARCHAR(100),
    priority            VARCHAR(10)     NOT NULL CHECK (priority IN ('High', 'Medium', 'Low')),
    is_active           BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_distributors_code
    ON distributors (distributor_code);

CREATE INDEX IF NOT EXISTS idx_distributors_priority
    ON distributors (priority);

CREATE INDEX IF NOT EXISTS idx_distributors_active
    ON distributors (is_active);


-- =============================================================
-- 2. SKUS
-- Master catalogue of all SKUs
-- =============================================================
CREATE TABLE IF NOT EXISTS skus (
    sku_id                  UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    sku_code                VARCHAR(100)    NOT NULL UNIQUE,
    sku_name                VARCHAR(255)    NOT NULL,
    sku_description         TEXT,
    category                VARCHAR(100),
    brand_family            VARCHAR(100),
    oem                     VARCHAR(100),
    priority                VARCHAR(20),
    pack_size               VARCHAR(50),
    variant_type            VARCHAR(100),
    unit_cost               NUMERIC(12, 2),
    recommendation_strategy VARCHAR(255),
    target_channel          VARCHAR(100),
    rationale               TEXT,
    is_new_product          BOOLEAN         NOT NULL DEFAULT FALSE,
    unit_of_measure         VARCHAR(50)     NOT NULL DEFAULT 'units',
    is_active               BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_skus_code
    ON skus (sku_code);

CREATE INDEX IF NOT EXISTS idx_skus_category
    ON skus (category);

CREATE INDEX IF NOT EXISTS idx_skus_brand_family
    ON skus (brand_family);

CREATE INDEX IF NOT EXISTS idx_skus_new_product
    ON skus (is_new_product);


-- =============================================================
-- 3. DISTRIBUTOR_SKUS
-- Which SKUs each distributor handles
-- =============================================================
CREATE TABLE IF NOT EXISTS distributor_skus (
    id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id  UUID            NOT NULL REFERENCES distributors (distributor_id) ON DELETE CASCADE,
    sku_id          UUID            NOT NULL REFERENCES skus (sku_id) ON DELETE CASCADE,
    is_active       BOOLEAN         NOT NULL DEFAULT TRUE,
    assigned_at     TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_distributor_sku UNIQUE (distributor_id, sku_id)
);

CREATE INDEX IF NOT EXISTS idx_dist_skus_distributor
    ON distributor_skus (distributor_id);

CREATE INDEX IF NOT EXISTS idx_dist_skus_sku
    ON distributor_skus (sku_id);


-- =============================================================
-- 4. DEMAND_CYCLES
-- One row per monthly planning cycle
-- =============================================================
CREATE TABLE IF NOT EXISTS demand_cycles (
    cycle_id        UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    cycle_date      DATE            NOT NULL UNIQUE,
    cycle_label     VARCHAR(50)     NOT NULL,
    status          VARCHAR(20)     NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'in_progress', 'closed')),
    started_at      TIMESTAMPTZ,
    closed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_demand_cycles_date
    ON demand_cycles (cycle_date);

CREATE INDEX IF NOT EXISTS idx_demand_cycles_status
    ON demand_cycles (status);


-- =============================================================
-- 5. PRIMARY_SALES
-- Historical cleaned data loaded from your main sales file
-- This is the source used by context + recommendation logic
-- =============================================================
CREATE TABLE IF NOT EXISTS primary_sales (
    sale_id              UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id       UUID            NOT NULL REFERENCES distributors (distributor_id) ON DELETE CASCADE,
    sku_id               UUID            NOT NULL REFERENCES skus (sku_id) ON DELETE CASCADE,
    cycle_id             UUID            REFERENCES demand_cycles (cycle_id) ON DELETE SET NULL,

    -- Historical sales fields
    sales_qty            NUMERIC(12, 2)  NOT NULL DEFAULT 0 CHECK (sales_qty >= 0),
    gross_dispatch_value NUMERIC(12, 2)  DEFAULT 0 CHECK (gross_dispatch_value >= 0),
    sale_date            DATE,
    transaction_date     DATE,

    -- Optional planning fields
    confirmed_30d_qty    NUMERIC(12, 2)  CHECK (confirmed_30d_qty >= 0),
    week1_qty            NUMERIC(12, 2)  CHECK (week1_qty >= 0),
    week2_qty            NUMERIC(12, 2)  CHECK (week2_qty >= 0),
    week3_qty            NUMERIC(12, 2)  CHECK (week3_qty >= 0),
    week4_qty            NUMERIC(12, 2)  CHECK (week4_qty >= 0),

    validation_status    VARCHAR(20)     NOT NULL DEFAULT 'pending'
                            CHECK (validation_status IN ('pending', 'passed', 'failed', 'under_review')),

    created_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_primary_sales_distributor
    ON primary_sales (distributor_id);

CREATE INDEX IF NOT EXISTS idx_primary_sales_sku
    ON primary_sales (sku_id);

CREATE INDEX IF NOT EXISTS idx_primary_sales_cycle
    ON primary_sales (cycle_id);

CREATE INDEX IF NOT EXISTS idx_primary_sales_sale_date
    ON primary_sales (sale_date);

CREATE INDEX IF NOT EXISTS idx_primary_sales_txn_date
    ON primary_sales (transaction_date);

CREATE INDEX IF NOT EXISTS idx_primary_sales_val_status
    ON primary_sales (validation_status);


-- =============================================================
-- 6. DEMAND_RECORDS
-- Final suggested + confirmed demand per distributor, SKU, cycle
-- Written after reply parsing and demand planning
-- =============================================================
CREATE TABLE IF NOT EXISTS demand_records (
    demand_id               UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    distributor_id          UUID            NOT NULL REFERENCES distributors (distributor_id) ON DELETE CASCADE,
    sku_id                  UUID            NOT NULL REFERENCES skus (sku_id) ON DELETE CASCADE,
    cycle_id                UUID            NOT NULL REFERENCES demand_cycles (cycle_id) ON DELETE CASCADE,

    suggested_qty           NUMERIC(12, 2)  NOT NULL DEFAULT 0 CHECK (suggested_qty >= 0),
    confirmed_qty           NUMERIC(12, 2)  CHECK (confirmed_qty >= 0),

    confirmed_30d_qty       NUMERIC(12, 2)  CHECK (confirmed_30d_qty >= 0),
    week1_qty               NUMERIC(12, 2)  CHECK (week1_qty >= 0),
    week2_qty               NUMERIC(12, 2)  CHECK (week2_qty >= 0),
    week3_qty               NUMERIC(12, 2)  CHECK (week3_qty >= 0),
    week4_qty               NUMERIC(12, 2)  CHECK (week4_qty >= 0),

    demand_status_locked    BOOLEAN         NOT NULL DEFAULT FALSE,
    reply_latency_days      NUMERIC(5, 2),

    email_sent_at           TIMESTAMPTZ,
    reply_received_at       TIMESTAMPTZ,
    resend_message_id       VARCHAR(255),

    validation_status       VARCHAR(20)     NOT NULL DEFAULT 'pending'
                                CHECK (validation_status IN ('pending', 'passed', 'failed', 'under_review')),

    temporal_workflow_id    VARCHAR(255),

    created_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_demand_dist_sku_cycle UNIQUE (distributor_id, sku_id, cycle_id)
);

CREATE INDEX IF NOT EXISTS idx_demand_records_distributor
    ON demand_records (distributor_id);

CREATE INDEX IF NOT EXISTS idx_demand_records_sku
    ON demand_records (sku_id);

CREATE INDEX IF NOT EXISTS idx_demand_records_cycle
    ON demand_records (cycle_id);

CREATE INDEX IF NOT EXISTS idx_demand_records_locked
    ON demand_records (demand_status_locked);

CREATE INDEX IF NOT EXISTS idx_demand_records_val_status
    ON demand_records (validation_status);

CREATE INDEX IF NOT EXISTS idx_demand_records_email_sent
    ON demand_records (email_sent_at);


-- =============================================================
-- 7. VALIDATION_RESULTS
-- Validation output for each demand record
-- =============================================================
CREATE TABLE IF NOT EXISTS validation_results (
    validation_id       UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    demand_id           UUID            NOT NULL REFERENCES demand_records (demand_id) ON DELETE CASCADE,

    sku_valid           BOOLEAN         NOT NULL DEFAULT FALSE,
    distributor_valid   BOOLEAN         NOT NULL DEFAULT FALSE,
    qty_sanity_passed   BOOLEAN         NOT NULL DEFAULT FALSE,
    duplicate_check     BOOLEAN         NOT NULL DEFAULT FALSE,
    format_check        BOOLEAN         NOT NULL DEFAULT FALSE,

    overall_status      VARCHAR(20)     NOT NULL DEFAULT 'pending'
                            CHECK (overall_status IN ('pending', 'passed', 'failed')),

    failure_reason      TEXT,
    validated_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_validation_demand
    ON validation_results (demand_id);

CREATE INDEX IF NOT EXISTS idx_validation_status
    ON validation_results (overall_status);


-- =============================================================
-- 8. REVIEW_QUEUE
-- Failed validations go here for manual review
-- =============================================================
CREATE TABLE IF NOT EXISTS review_queue (
    review_id        UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    demand_id        UUID            NOT NULL REFERENCES demand_records (demand_id) ON DELETE CASCADE,
    validation_id    UUID            NOT NULL REFERENCES validation_results (validation_id) ON DELETE CASCADE,

    failure_summary  TEXT            NOT NULL,
    status           VARCHAR(20)     NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'approved', 'rejected')),

    reviewed_by      VARCHAR(255),
    reviewed_at      TIMESTAMPTZ,
    review_notes     TEXT,

    queued_at        TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_review_queue_demand
    ON review_queue (demand_id);

CREATE INDEX IF NOT EXISTS idx_review_queue_status
    ON review_queue (status);


-- =============================================================
-- AUTO-UPDATE updated_at TRIGGER
-- =============================================================
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS set_updated_at_distributors ON distributors;
CREATE TRIGGER set_updated_at_distributors
    BEFORE UPDATE ON distributors
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();

DROP TRIGGER IF EXISTS set_updated_at_skus ON skus;
CREATE TRIGGER set_updated_at_skus
    BEFORE UPDATE ON skus
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();

DROP TRIGGER IF EXISTS set_updated_at_primary_sales ON primary_sales;
CREATE TRIGGER set_updated_at_primary_sales
    BEFORE UPDATE ON primary_sales
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();

DROP TRIGGER IF EXISTS set_updated_at_demand_records ON demand_records;
CREATE TRIGGER set_updated_at_demand_records
    BEFORE UPDATE ON demand_records
    FOR EACH ROW
    EXECUTE FUNCTION trigger_set_updated_at();


INSERT INTO distributors (
    distributor_code,
    name,
    email,
    region,
    priority
)
VALUES
('D01', 'Revan', 'revanbejagam@gmail.com', 'South', 'High'),
('D02', 'Rishitha', 'rishithareddyc2002@gmail.com', 'South', 'Medium'),
('D03', 'Phani', 'lingaphani21@gmail.com', 'South', 'Medium')
ON CONFLICT (distributor_code) DO NOTHING;