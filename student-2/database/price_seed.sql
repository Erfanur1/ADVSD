INSERT INTO price_history (market_ticker, ts, yes_price)
WITH RECURSIVE walk(ticker, day, price) AS (
    SELECT market_ticker, 0,
           CASE side WHEN 'YES' THEN entry_price ELSE 1 - entry_price END
    FROM positions GROUP BY market_ticker
    UNION ALL
    SELECT ticker, day + 1,
           MIN(0.99, MAX(0.01, price + ((abs(random()) % 7) - 3) / 100.0))
    FROM walk WHERE day < 29
)
SELECT ticker, date('now', '-' || (29 - day) || ' days'), ROUND(price, 3) FROM walk;