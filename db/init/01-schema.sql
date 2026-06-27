CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS sen_readings (
    collected_at    TIMESTAMPTZ NOT NULL,
    source_ts       TIMESTAMPTZ,

    prod            DOUBLE PRECISION,
    cons            DOUBLE PRECISION,
    cons15          DOUBLE PRECISION,
    cons2           DOUBLE PRECISION,
    sold            DOUBLE PRECISION,
    plan            DOUBLE PRECISION,

    eolian          DOUBLE PRECISION,
    eolian15        DOUBLE PRECISION,
    foto            DOUBLE PRECISION,
    foto15          DOUBLE PRECISION,
    ape             DOUBLE PRECISION,
    nucl            DOUBLE PRECISION,
    nucl15          DOUBLE PRECISION,
    gaze            DOUBLE PRECISION,
    gaze15          DOUBLE PRECISION,
    carb            DOUBLE PRECISION,
    carb15          DOUBLE PRECISION,
    bmasa           DOUBLE PRECISION,
    bmasa15         DOUBLE PRECISION,
    cose            DOUBLE PRECISION,

    dobr            DOUBLE PRECISION,
    dobr15          DOUBLE PRECISION,
    djer            DOUBLE PRECISION,
    djer15          DOUBLE PRECISION,
    varn            DOUBLE PRECISION,
    varn15          DOUBLE PRECISION,
    kozl1           DOUBLE PRECISION,
    kozl115         DOUBLE PRECISION,
    kozl2           DOUBLE PRECISION,
    kozl215         DOUBLE PRECISION,
    pancevo21       DOUBLE PRECISION,
    pancevo2115     DOUBLE PRECISION,
    pancevo22       DOUBLE PRECISION,
    pancevo2215     DOUBLE PRECISION,
    unge            DOUBLE PRECISION,
    muka            DOUBLE PRECISION,
    muka15          DOUBLE PRECISION,
    beke1           DOUBLE PRECISION,
    beke115         DOUBLE PRECISION,
    sand            DOUBLE PRECISION,
    sand15          DOUBLE PRECISION,
    is_line         DOUBLE PRECISION,
    ias2            DOUBLE PRECISION,
    ias215          DOUBLE PRECISION,
    paro            DOUBLE PRECISION,
    paro15          DOUBLE PRECISION,
    cioa            DOUBLE PRECISION,
    chef            DOUBLE PRECISION,
    chef15          DOUBLE PRECISION,
    chea            DOUBLE PRECISION,
    chea15          DOUBLE PRECISION,
    gote            DOUBLE PRECISION,
    mint            DOUBLE PRECISION,
    mint15          DOUBLE PRECISION,
    kiki            DOUBLE PRECISION,

    s110            DOUBLE PRECISION,
    sip             DOUBLE PRECISION,
    kusj            DOUBLE PRECISION,
    ispoz           DOUBLE PRECISION,
    vulc            DOUBLE PRECISION,
    prog            DOUBLE PRECISION,
    prot1tms        DOUBLE PRECISION,

    PRIMARY KEY (collected_at)
);

SELECT create_hypertable(
    'sen_readings',
    'collected_at',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

CREATE MATERIALIZED VIEW IF NOT EXISTS sen_5min
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('5 minutes', collected_at) AS bucket,
    AVG(prod) AS prod,
    AVG(cons) AS cons,
    AVG(cons2) AS cons2,
    AVG(sold) AS sold,
    AVG(eolian) AS eolian,
    AVG(foto) AS foto,
    AVG(ape) AS ape,
    AVG(nucl) AS nucl,
    AVG(gaze) AS gaze,
    AVG(carb) AS carb,
    AVG(bmasa) AS bmasa,
    AVG(cose) AS cose
FROM sen_readings
GROUP BY bucket
WITH NO DATA;

SELECT add_continuous_aggregate_policy(
    'sen_5min',
    start_offset => INTERVAL '1 hour',
    end_offset => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '5 minutes',
    if_not_exists => TRUE
);

SELECT add_retention_policy(
    'sen_readings',
    INTERVAL '90 days',
    if_not_exists => TRUE
);
