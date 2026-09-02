INSERT INTO portfolios (name, currency) VALUES ('Main Portfolio', 'USD');
INSERT INTO portfolios (name, currency) VALUES ('Crypto YOLO', 'USD');
INSERT INTO portfolios (name, currency) VALUES ('Politics 2026', 'USD');
INSERT INTO portfolios (name, currency) VALUES ('Sports Arbitrage', 'USD');
INSERT INTO portfolios (name, currency) VALUES ('Macro Hedge', 'USD');
INSERT INTO portfolios (name, currency) VALUES ('Tech & Science', 'USD');
INSERT INTO portfolios (name, currency) VALUES ('Climate Watch', 'USD');
INSERT INTO portfolios (name, currency) VALUES ('Entertainment Bets', 'USD');
INSERT INTO portfolios (name, currency) VALUES ('World Events', 'USD');
INSERT INTO portfolios (name, currency) VALUES ('Business & IPOs', 'USD');

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

INSERT INTO trade_history (position_id, trade_type, shares, price) VALUES
(1, 'BUY', 100, 0.55),
(2, 'BUY', 300, 0.18),
(2, 'BUY', 200, 0.22),
(3, 'BUY', 200, 0.15),
(4, 'BUY', 50, 0.40),
(5, 'BUY', 150, 0.45),
(6, 'BUY', 300, 0.60),
(7, 'BUY', 1000, 0.10),
(8, 'BUY', 50, 0.05),
(9, 'BUY', 75, 0.25),
(10, 'BUY', 400, 0.70),
(1, 'SELL', 20, 0.58);
