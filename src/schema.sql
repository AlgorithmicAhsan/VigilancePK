-- Vigilance-PK database schema (Neon Postgres). Safe to run repeatedly:
-- every statement is IF NOT EXISTS. See ADR-028.

-- People who log in to the dashboard. Admins manage lists and users;
-- reviewers approve news entries. Machines (the cron sync) use ADMIN_KEY.
CREATE TABLE IF NOT EXISTS users (
    id            serial PRIMARY KEY,
    username      text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role          text NOT NULL CHECK (role IN ('admin', 'reviewer')),
    active        boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Every editable list in one table, so the client can change sources and
-- taxonomy from the dashboard without code changes. Rows are deactivated,
-- never deleted, so past entries keep their meaning.
CREATE TABLE IF NOT EXISTS lookups (
    id         serial PRIMARY KEY,
    kind       text NOT NULL CHECK (kind IN
               ('newspaper', 'feed', 'category', 'sub_category', 'keyword', 'news_type', 'province', 'city')),
    hrms_id    int,             -- the client's own ID, so exports line up with their system
    name       text NOT NULL,
    parent     text,            -- feed -> its newspaper; city -> its province
    url        text,            -- feed: RSS address
    language   text,            -- newspaper
    city       text,            -- newspaper: edition city
    frequency  text,            -- newspaper: Daily, Weekly...
    control    text,            -- HRMS "Control Options": ShowonBoth / ShowonReport
    active     boolean NOT NULL DEFAULT true,
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS lookups_kind_hrms_id ON lookups (kind, hrms_id) WHERE hrms_id IS NOT NULL;
-- Names are unique ignoring case: "Police excesses" and "police excesses"
-- would give the AI two identical choices with different IDs.
CREATE UNIQUE INDEX IF NOT EXISTS lookups_kind_name ON lookups (kind, lower(name));

-- One row per news story, columns in the order of the client's
-- "News Information" form. Dropdowns keep both the HRMS ID and the name so
-- the client's export script can use whichever their table expects.
CREATE TABLE IF NOT EXISTS news_entries (
    news_date            date NOT NULL,            -- Date
    newspaper_id         int  NOT NULL,            -- Newspaper (HRMS ID)
    newspaper            text NOT NULL,
    frequency            text NOT NULL,            -- Frequency
    language             text NOT NULL,            -- Language
    newspaper_city       text NOT NULL,            -- News Paper City
    news_type            text NOT NULL,            -- News Type
    writer               text NOT NULL,            -- Writer
    city                 text NOT NULL,            -- City
    province             text NOT NULL,            -- Province
    location             text,                     -- Location/Mohalla
    headline             text NOT NULL,            -- Headlines
    headline_translated  text,                     -- AI translated
    main_category_id     int  NOT NULL,            -- Main Category (HRMS ID)
    main_category        text NOT NULL,
    sub_category_1_id    int,                      -- Sub Category One
    sub_category_1       text,
    sub_category_2_id    int,                      -- Sub Category Two
    sub_category_2       text,
    sub_category_3_id    int,                      -- Sub Category Three
    sub_category_3       text,
    external_link        text NOT NULL UNIQUE,     -- External Link; also blocks duplicates
    keyword_ids          int[] NOT NULL CHECK (cardinality(keyword_ids) > 0),  -- Keywords (HRMS IDs)
    keywords             text NOT NULL,            -- keyword names, comma-separated
    meta_description     text,                     -- Meta Description
    news_details         text,                     -- News Details

    -- Tracking, kept after the form fields.
    id           uuid PRIMARY KEY,                 -- uuid5 of the link
    status       text NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending', 'approved', 'rejected', 'exported')),
    ai_reasoning text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    reviewed_by  text,
    reviewed_at  timestamptz,
    exported_at  timestamptz
);
CREATE INDEX IF NOT EXISTS news_entries_status_date ON news_entries (status, news_date DESC);
