INSERT INTO categories (name) VALUES
 ('Politics'),('Sports'),('Crypto'),('Economics'),('Technology'),
 ('Entertainment'),('Science'),('Climate'),('Business'),('World');

INSERT INTO markets (title, category, current_probability, volume, close_date) VALUES
 ('US presidential incumbent party retains White House', 'Politics', 0.52, 480000, '2028-11-07'),
 ('Bitcoin above $100k by year end', 'Crypto', 0.41, 920000, '2026-12-31'),
 ('Fed cuts rates at next meeting', 'Economics', 0.63, 350000, '2026-09-18'),
 ('Home team wins the grand final', 'Sports', 0.55, 210000, '2026-10-04'),
 ('New flagship phone ships on time', 'Technology', 0.72, 88000, '2026-09-30'),
 ('Blockbuster tops $1B opening month', 'Entertainment', 0.34, 65000, '2026-12-20'),
 ('Fusion net-energy milestone announced', 'Science', 0.18, 42000, '2027-06-30'),
 ('Global avg temp record broken this year', 'Climate', 0.66, 130000, '2026-12-31'),
 ('Major IPO prices above range', 'Business', 0.47, 76000, '2026-11-15'),
 ('Trade deal signed before deadline', 'World', 0.39, 54000, '2026-10-31'),
 ('Ethereum above $6k by year end', 'Crypto', 0.29, 610000, '2026-12-31'),
 ('Unemployment falls below 4%', 'Economics', 0.44, 190000, '2026-12-31');

INSERT INTO watchlist (market_id, note, priority) VALUES
 (1,'Watching swing-state polling',3),(2,'Momentum on halving narrative',2),
 (3,'Key macro event',3),(4,'Home advantage',1),(5,'Supply-chain risk',1),
 (6,'Long shot',0),(7,'Speculative',0),(8,'High conviction',2),
 (9,'Track roadshow',1),(10,'Geopolitics dependent',2);
