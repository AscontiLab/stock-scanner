BEGIN TRANSACTION;
CREATE TABLE cfd_scan_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date       TEXT    NOT NULL,
    scanned_at      TEXT    NOT NULL,
    fear_greed      INTEGER,
    ticker_count    INTEGER,
    long_signals    INTEGER DEFAULT 0,
    short_signals   INTEGER DEFAULT 0,
    notes           TEXT
);
INSERT INTO "cfd_scan_runs" VALUES(1,'2026-03-12','2026-03-12T12:33:40.175078',50,657,10,10,NULL);
INSERT INTO "cfd_scan_runs" VALUES(2,'2026-03-13','2026-03-13T06:33:15.101491',50,657,10,10,NULL);
INSERT INTO "cfd_scan_runs" VALUES(3,'2026-03-13','2026-03-13T22:32:10.142795',50,657,10,10,NULL);
CREATE TABLE cfd_signals (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id            INTEGER NOT NULL REFERENCES cfd_scan_runs(id),

    -- Signal-Identifikation
    ticker            TEXT    NOT NULL,
    market            TEXT,
    direction         TEXT    NOT NULL,    -- "long" | "short"

    -- Scoring
    quality_score     REAL    NOT NULL,    -- gewichteter Score (0-10)
    adx               REAL,
    plus_di           REAL,
    minus_di          REAL,
    rsi               REAL,
    vol_ratio         REAL,
    atr_pct           REAL,
    trend_days        INTEGER,            -- Trend-Reife in Tagen
    recent_max_gap    REAL,

    -- Levels
    entry_price       REAL    NOT NULL,
    stop_price        REAL    NOT NULL,
    tp1_price         REAL    NOT NULL,
    tp2_price         REAL    NOT NULL,

    -- Indikator-Snapshot (JSON)
    indicators_json   TEXT,

    -- Resolution (befuellt nach Aufloesung)
    resolved_at       TEXT,
    outcome           TEXT,               -- "stop" | "tp1" | "tp2" | "expired" | NULL
    outcome_day       INTEGER,            -- an welchem Trading-Tag
    exit_price        REAL,
    pnl_r             REAL,               -- P&L in R-Multiples (-1.0, +1.0, +2.67)
    max_favorable     REAL,               -- maximaler Gewinn in R
    max_adverse       REAL                -- maximaler Drawdown in R
);
INSERT INTO "cfd_signals" VALUES(1,1,'PSX','S&P 500','long',8.5,45.5,30.2,10.4,71.2,1.25,3.22,9,4.3,169.5,161.32,177.68,191.3,'{"macd": "bullish", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=6.944)", "vwap": "BUY (159.24)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(2,1,'SDF.DE','MDAX','long',8.5,40.8,37.0,7.6,80.5,2.54,3.38,10,9.3,16.99,16.13,17.85,19.29,'{"macd": "bullish", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=1.239)", "vwap": "BUY (15.21)", "ema9_gt_ema21": true}','2026-03-13T22:32:11.043811','tp1',1,17.85,1.0,1.98,0.0);
INSERT INTO "cfd_signals" VALUES(3,1,'AEP','NASDAQ 100','long',8.0,41.0,25.1,13.5,60.9,0.66,1.79,10,1.1,131.26,127.73,134.79,140.67,'{"macd": "bearish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=3.017)", "vwap": "BUY (130.49)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(4,1,'CF','S&P 500','long',8.0,41.9,40.9,13.3,74.5,1.48,5.29,10,9.2,120.13,110.59,129.67,145.57,'{"macd": "bullish", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=10.322)", "vwap": "BUY (106.16)", "ema9_gt_ema21": true}','2026-03-13T22:32:11.050170','tp1',1,129.67,1.0,1.39,0.0);
INSERT INTO "cfd_signals" VALUES(5,1,'EOG','S&P 500','long',8.0,43.8,34.1,15.4,69.1,0.86,2.97,10,3.6,132.51,126.61,138.41,148.24,'{"macd": "bullish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=6.268)", "vwap": "BUY (124.94)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(6,1,'SBUX','NASDAQ 100','long',7.5,32.7,26.5,14.7,66.5,1.13,2.66,10,1.6,101.44,97.39,105.49,112.24,'{"macd": "bullish", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=3.812)", "vwap": "BUY (97.23)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(7,1,'CTVA','S&P 500','long',7.5,35.3,22.6,16.7,58.9,0.76,2.45,9,3.0,78.63,75.74,81.52,86.33,'{"macd": "bearish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=0.984)", "vwap": "BUY (77.04)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(8,1,'CTRA','S&P 500','long',7.5,35.6,27.1,16.5,59.7,1.29,3.29,7,3.8,31.35,29.8,32.9,35.47,'{"macd": "bearish", "ma": "BUY", "bollinger": "neutral", "squeeze": "Squeeze ON", "vwap": "BUY (30.87)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(9,1,'DVA','S&P 500','long',7.5,41.9,31.6,14.7,64.8,1.39,3.36,10,3.1,154.81,147.0,162.62,175.64,'{"macd": "bearish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=5.451)", "vwap": "BUY (150.47)", "ema9_gt_ema21": true}','2026-03-13T22:32:11.055413','stop',1,147.0,-1.0,0.0,1.12);
INSERT INTO "cfd_signals" VALUES(10,1,'DLR','S&P 500','long',7.5,30.0,23.1,14.4,60.2,1.34,2.46,9,2.0,180.59,173.92,187.26,198.37,'{"macd": "bearish", "ma": "BUY", "bollinger": "neutral", "squeeze": "Squeeze ON", "vwap": "BUY (178.54)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(11,1,'ARES','S&P 500','short',8.0,51.0,10.3,37.1,27.0,1.3,6.56,10,6.0,103.46,113.65,93.27,76.3,'{"macd": "SELL", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-16.599)", "vwap": "SELL (118.65)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(12,1,'BX','S&P 500','short',8.0,45.8,11.2,36.4,29.1,0.91,5.57,10,4.5,107.25,116.21,98.29,83.36,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-12.285)", "vwap": "SELL (117.77)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(13,1,'COF','S&P 500','short',8.0,40.8,12.3,37.4,30.9,0.87,4.77,10,3.4,182.02,195.04,169.0,147.31,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-17.868)", "vwap": "SELL (197.60)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(14,1,'CBRE','S&P 500','short',8.0,40.0,9.7,40.2,29.3,0.8,3.74,10,3.1,132.49,139.93,125.05,112.66,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (squeeze)", "squeeze": "SELL (mom=-14.645)", "vwap": "SELL (143.31)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(15,1,'EXPD','S&P 500','short',8.0,41.4,13.1,34.7,37.5,0.62,3.72,10,2.7,140.81,148.66,132.96,119.87,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-6.698)", "vwap": "SELL (145.89)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(16,1,'STE','S&P 500','short',8.0,36.0,11.5,43.7,25.0,1.68,2.79,8,3.4,221.55,230.82,212.28,196.84,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (below lower)", "squeeze": "SELL (mom=-19.361)", "vwap": "SELL (241.80)", "ema9_gt_ema21": false}','2026-03-13T22:32:11.061900','tp1',1,212.28,1.0,1.25,0.0);
INSERT INTO "cfd_signals" VALUES(17,1,'WAT','S&P 500','short',8.0,45.0,10.7,34.9,29.5,0.46,3.48,10,4.1,297.54,313.07,282.01,256.13,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (squeeze)", "squeeze": "SELL (mom=-20.232)", "vwap": "SELL (319.37)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(18,1,'IDXX','NASDAQ 100','short',7.5,33.0,10.7,30.5,35.0,0.81,3.43,7,4.6,600.52,631.39,569.65,518.19,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-30.746)", "vwap": "SELL (631.09)", "ema9_gt_ema21": false}','2026-03-13T22:32:11.065199','tp1',1,569.65,1.0,1.07,0.0);
INSERT INTO "cfd_signals" VALUES(19,1,'ZS','NASDAQ 100','short',7.5,36.6,18.2,31.8,39.2,0.68,7.06,8,3.7,153.81,170.1,137.52,110.37,'{"macd": "bullish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-6.639)", "vwap": "SELL (157.60)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(20,1,'MDT','S&P 500','short',7.5,30.1,9.2,34.1,25.4,0.89,2.39,5,2.7,88.97,92.16,85.78,80.46,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (below lower)", "squeeze": "SELL (mom=-6.207)", "vwap": "SELL (96.08)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(21,2,'CVX','S&P 500','long',9.0,44.9,38.2,13.2,72.3,2.3,2.11,10,3.0,196.97,190.73,203.21,213.61,'{"macd": "BUY", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=7.395)", "vwap": "BUY (187.50)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(22,2,'PSX','S&P 500','long',9.0,46.7,38.2,9.2,74.9,2.01,3.37,10,4.3,174.09,165.29,182.89,197.57,'{"macd": "bullish", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=10.578)", "vwap": "BUY (160.72)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(23,2,'CF','S&P 500','long',8.5,43.6,51.7,10.8,81.9,2.85,5.3,10,13.2,136.0,125.18,146.82,164.84,'{"macd": "bullish", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=19.506)", "vwap": "BUY (110.19)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(24,2,'ENI.MI','Euro Stoxx 50','long',8.5,56.6,51.1,6.4,85.3,1.28,2.32,10,2.3,21.76,21.01,22.52,23.79,'{"macd": "bullish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=1.839)", "vwap": "BUY (19.86)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(25,2,'SDF.DE','MDAX','long',8.5,41.3,44.4,6.7,84.2,5.18,3.62,10,14.8,17.84,16.87,18.81,20.42,'{"macd": "bullish", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=1.578)", "vwap": "BUY (15.57)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(26,2,'ROST','NASDAQ 100','long',8.0,40.4,31.0,18.8,61.7,0.8,2.85,10,1.4,209.84,200.86,218.82,233.79,'{"macd": "bullish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=6.218)", "vwap": "BUY (205.24)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(27,2,'SBUX','NASDAQ 100','long',8.0,32.7,26.7,13.7,61.0,1.52,2.67,10,1.2,100.18,96.17,104.19,110.88,'{"macd": "bullish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=3.105)", "vwap": "BUY (97.47)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(28,2,'COP','S&P 500','long',8.0,33.5,36.1,17.8,68.3,1.25,2.91,10,2.8,120.26,115.02,125.5,134.24,'{"macd": "BUY", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=4.226)", "vwap": "BUY (114.52)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(29,2,'DVA','S&P 500','long',8.0,41.7,31.9,13.7,61.6,1.44,3.44,10,2.2,153.06,145.17,160.95,174.09,'{"macd": "bearish", "ma": "BUY", "bollinger": "neutral", "squeeze": "Squeeze ON", "vwap": "BUY (151.21)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(30,2,'EOG','S&P 500','long',8.0,44.0,38.4,14.3,69.7,0.92,3.04,10,3.6,133.04,126.97,139.11,149.23,'{"macd": "bullish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=6.807)", "vwap": "BUY (125.71)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(31,2,'ARES','S&P 500','short',8.5,51.7,9.4,38.7,23.3,2.07,7.05,10,6.7,96.5,106.7,86.3,69.31,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (below lower)", "squeeze": "SELL (mom=-19.029)", "vwap": "SELL (115.79)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(32,2,'BX','S&P 500','short',8.5,46.7,10.4,38.6,25.4,1.49,5.84,10,4.8,102.12,111.07,93.17,78.25,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-14.365)", "vwap": "SELL (116.23)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(33,2,'DHR','S&P 500','short',8.5,47.2,7.2,40.2,23.0,1.24,2.57,10,4.5,186.26,193.44,179.08,167.11,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (below lower)", "squeeze": "SELL (mom=-14.778)", "vwap": "SELL (205.12)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(34,2,'HEI.DE','DAX 40','short',8.5,41.8,15.5,49.1,24.2,1.32,5.12,10,4.5,162.65,175.15,150.15,129.32,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-20.152)", "vwap": "SELL (187.52)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(35,2,'IDXX','NASDAQ 100','short',8.0,34.6,9.6,32.5,28.4,1.52,3.82,8,4.9,571.21,603.93,538.49,483.96,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (below lower)", "squeeze": "SELL (mom=-42.898)", "vwap": "SELL (626.61)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(36,2,'MELI','NASDAQ 100','short',8.0,35.5,12.3,35.8,31.7,1.69,5.53,10,4.9,1680.0,1819.39,1540.61,1308.31,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-149.879)", "vwap": "SELL (1801.38)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(37,2,'BAC','S&P 500','short',8.0,30.2,14.5,34.2,30.9,1.23,3.54,10,2.9,47.13,49.64,44.62,40.45,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-2.683)", "vwap": "SELL (50.16)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(38,2,'TECH','S&P 500','short',8.0,39.8,7.7,33.8,31.8,1.45,5.1,10,4.0,51.47,55.41,47.53,40.97,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (below lower)", "squeeze": "SELL (mom=-4.886)", "vwap": "SELL (56.58)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(39,2,'BLDR','S&P 500','short',8.0,31.9,11.7,35.5,24.0,1.35,5.41,8,5.0,86.6,93.62,79.58,67.87,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-16.501)", "vwap": "SELL (102.89)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(40,2,'COF','S&P 500','short',8.0,41.8,11.6,39.4,28.4,1.07,4.87,10,3.4,177.45,190.41,164.49,142.89,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-18.326)", "vwap": "SELL (195.76)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(41,3,'ENI.MI','Euro Stoxx 50','long',8.5,58.3,54.6,5.8,87.4,1.29,2.36,10,2.7,22.35,21.56,23.14,24.46,'{"macd": "bullish", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=2.125)", "vwap": "BUY (20.07)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(42,3,'TTE.PA','Euro Stoxx 50','long',8.5,53.2,43.9,11.5,77.8,1.38,2.53,10,2.7,72.33,69.58,75.08,79.66,'{"macd": "bullish", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=3.768)", "vwap": "BUY (68.06)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(43,3,'SDF.DE','MDAX','long',8.5,43.9,47.2,6.1,85.6,2.38,3.76,10,14.8,18.26,17.23,19.29,21.01,'{"macd": "bullish", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=2.226)", "vwap": "BUY (15.92)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(44,3,'CF','S&P 500','long',8.0,44.8,45.7,11.2,72.7,1.47,6.01,10,13.2,129.57,117.88,141.26,160.74,'{"macd": "bullish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=22.199)", "vwap": "BUY (111.95)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(45,3,'CVX','S&P 500','long',8.0,45.1,36.1,12.5,71.9,0.89,2.12,10,3.0,196.82,190.55,203.09,213.53,'{"macd": "bullish", "ma": "BUY", "bollinger": "SELL (above upper)", "squeeze": "BUY (mom=9.408)", "vwap": "BUY (188.14)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(46,3,'KEYS','S&P 500','long',8.0,40.6,30.1,20.3,57.5,0.8,6.12,10,3.5,279.78,254.11,305.45,348.22,'{"macd": "bearish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=7.448)", "vwap": "SELL (283.16)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(47,3,'PSX','S&P 500','long',8.0,47.7,36.2,8.7,72.0,1.09,3.36,10,4.3,172.74,164.03,181.45,195.95,'{"macd": "bullish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=12.024)", "vwap": "BUY (161.54)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(48,3,'ROST','NASDAQ 100','long',7.5,38.4,28.9,22.3,55.2,0.9,2.91,10,1.7,206.28,197.27,215.29,230.3,'{"macd": "SELL", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=2.463)", "vwap": "BUY (205.69)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(49,3,'SBUX','NASDAQ 100','long',7.5,32.1,25.0,15.6,56.8,1.17,2.58,10,1.2,99.15,95.31,102.99,109.4,'{"macd": "bullish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=1.767)", "vwap": "BUY (97.60)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(50,3,'APA','S&P 500','long',7.5,34.5,37.1,11.7,73.3,0.86,4.29,10,3.6,34.47,32.25,36.69,40.38,'{"macd": "bullish", "ma": "BUY", "bollinger": "neutral", "squeeze": "BUY (mom=3.469)", "vwap": "BUY (30.80)", "ema9_gt_ema21": true}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(51,3,'TMO','S&P 500','short',8.5,48.8,7.1,37.2,24.4,1.39,3.1,10,4.0,464.37,485.99,442.75,406.71,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (below lower)", "squeeze": "SELL (mom=-36.639)", "vwap": "SELL (504.61)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(52,3,'TECH','S&P 500','short',8.0,41.5,7.2,32.0,30.7,0.96,4.97,10,4.0,50.85,54.64,47.06,40.74,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (below lower)", "squeeze": "SELL (mom=-5.226)", "vwap": "SELL (56.12)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(53,3,'DHR','S&P 500','short',8.0,48.9,6.8,39.2,25.0,0.99,2.52,10,4.5,187.32,194.4,180.24,168.43,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (below lower)", "squeeze": "SELL (mom=-16.457)", "vwap": "SELL (203.66)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(54,3,'ELV','S&P 500','short',8.0,42.9,11.6,28.4,38.2,0.85,4.38,10,3.1,291.63,310.8,272.46,240.51,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-15.627)", "vwap": "SELL (301.89)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(55,3,'EXPD','S&P 500','short',8.0,40.5,15.5,30.4,40.7,0.46,3.38,10,2.7,142.55,149.78,135.32,123.27,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-4.814)", "vwap": "SELL (145.28)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(56,3,'FOX','S&P 500','short',8.0,41.5,13.9,26.2,38.3,1.79,2.99,4,1.8,52.03,54.36,49.7,45.81,'{"macd": "bullish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-0.559)", "vwap": "BUY (51.96)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(57,3,'PRU','S&P 500','short',8.0,40.8,7.0,30.5,26.6,0.9,3.25,10,2.7,92.0,96.48,87.52,80.05,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-6.661)", "vwap": "SELL (98.96)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(58,3,'SYF','S&P 500','short',8.0,40.7,12.0,36.0,30.1,0.45,4.13,10,2.5,63.78,67.73,59.83,53.24,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-5.325)", "vwap": "SELL (69.40)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(59,3,'WAT','S&P 500','short',8.0,47.1,9.4,37.8,27.6,0.72,3.63,10,4.8,286.57,302.17,270.97,244.97,'{"macd": "bearish", "ma": "SELL", "bollinger": "BUY (squeeze)", "squeeze": "SELL (mom=-27.987)", "vwap": "SELL (315.07)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
INSERT INTO "cfd_signals" VALUES(60,3,'HEI.DE','DAX 40','short',8.0,42.5,15.0,48.0,23.5,0.87,5.1,10,4.5,161.0,173.32,148.68,128.16,'{"macd": "bearish", "ma": "SELL", "bollinger": "neutral", "squeeze": "SELL (mom=-22.833)", "vwap": "SELL (186.21)", "ema9_gt_ema21": false}',NULL,NULL,NULL,NULL,NULL,NULL,NULL);
CREATE INDEX idx_cfd_signals_ticker    ON cfd_signals(ticker);
CREATE INDEX idx_cfd_signals_outcome   ON cfd_signals(outcome);
CREATE INDEX idx_cfd_signals_direction ON cfd_signals(direction);
CREATE INDEX idx_cfd_signals_date      ON cfd_signals(run_id);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('cfd_scan_runs',3);
INSERT INTO "sqlite_sequence" VALUES('cfd_signals',60);
COMMIT;
