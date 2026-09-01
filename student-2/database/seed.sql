-- TODO(Student 2): seed >=10 records per table.
INSERT INTO portfolios (name, currency) VALUES ('Main Portfolio', 'USD');
INSERT INTO portfolios (name, currency) VALUES ('Crypto YOLO', 'USD');
INSERT INTO portfolios (name, currency) VALUES ('Politics 2026', 'USD');

INSERT INTO positions (portfolio_id, market_ticker, side, entry_price, size) VALUES 
(3, 'POL-TRUMP-2026', 'YES', 0.55, 100),
(1, 'KALSHI-FED-SEP', 'NO', 0.20, 500),
(3, 'POL-BIDEN-2026', 'NO', 0.15, 200),
(2, 'CRYPTO-BTC-100K', 'YES', 0.40, 50),
(3, 'POL-HARRIS-2026', 'YES', 0.45, 150),
(1, 'ECON-INFLATION-UP', 'YES', 0.60, 300),
(1, 'SPORTS-NFL-SB', 'NO', 0.10, 1000),
(3, 'POL-NEWSOM-2026', 'NO', 0.05, 50),
(2, 'CRYPTO-ETH-10K', 'YES', 0.25, 75),
(1, 'KALSHI-RATES-DOWN', 'YES', 0.70, 400);