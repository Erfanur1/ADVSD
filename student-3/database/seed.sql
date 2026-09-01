INSERT INTO sources (name, reliability_score) VALUES
 ('Reuters', 0.95),('Bloomberg', 0.93),('Associated Press', 0.94),
 ('CoinDesk', 0.78),('TechCrunch', 0.75),('The Athletic', 0.82),
 ('Nature News', 0.91),('Politico', 0.80),('Financial Times', 0.92),
 ('Ars Technica', 0.85);

INSERT INTO news_articles (headline, source_id, category, published_date, summary) VALUES
 ('Central bank signals possible rate move', 2, 'Economics', '2026-08-20', 'Officials hint at policy shift at next meeting, markets react.'),
 ('Major crypto exchange reports record volume', 4, 'Crypto', '2026-08-22', 'Trading volumes hit yearly high amid renewed retail interest.'),
 ('Election polling tightens in key swing states', 8, 'Politics', '2026-08-18', 'New surveys show a narrowing race with weeks to go.'),
 ('Flagship device launch delayed by supply issues', 5, 'Technology', '2026-08-15', 'Component shortages push back the release window.'),
 ('Championship favourite suffers injury setback', 6, 'Sports', '2026-08-24', 'Star player expected to miss upcoming fixtures.'),
 ('Breakthrough battery chemistry announced', 7, 'Science', '2026-08-19', 'Researchers report higher energy density in lab tests.'),
 ('Global shipping rates climb on route disruption', 1, 'World', '2026-08-21', 'Freight costs rise as carriers reroute around a chokepoint.'),
 ('Quarterly earnings beat analyst expectations', 9, 'Business', '2026-08-23', 'Strong consumer spending lifts results across sectors.'),
 ('Regulator opens review of major merger', 3, 'Business', '2026-08-17', 'Antitrust concerns raised over combined market share.'),
 ('New climate report warns of accelerating trend', 7, 'Climate', '2026-08-16', 'Data shows faster-than-expected warming in key regions.'),
 ('Streaming platform announces record subscriber growth', 5, 'Entertainment', '2026-08-25', 'Q3 additions exceed guidance on strength of new releases.'),
 ('Chipmaker unveils next-generation processor', 10, 'Technology', '2026-08-26', 'New architecture promises significant efficiency gains.');

INSERT INTO research_notes (article_id, title, content, tags) VALUES
 (1, 'Rate move implications', 'Watch for volatility in rate-sensitive markets.', 'macro,rates'),
 (2, 'Exchange volume spike', 'Correlates with renewed narrative around adoption.', 'crypto,volume'),
 (3, 'Swing state tracker', 'Polling error history suggests wide confidence interval.', 'politics,polling'),
 (4, 'Supply chain watch', 'Component shortage could push launch into next quarter.', 'tech,supply-chain'),
 (5, 'Injury impact', 'Line movement likely once official status confirmed.', 'sports,injury'),
 (6, 'Battery breakthrough follow-up', 'Lab results need independent replication before pricing in.', 'science,energy'),
 (7, 'Freight cost pass-through', 'Monitor downstream consumer price effects next quarter.', 'macro,shipping'),
 (8, 'Earnings beat context', 'Compare against sector peers reporting this week.', 'earnings,business'),
 (9, 'Merger review timeline', 'Regulatory review could take 6-12 months historically.', 'business,regulatory'),
 (10, 'Climate report follow-up', 'Cross-reference with related market close dates.', 'climate,report');
