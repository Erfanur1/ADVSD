INSERT INTO markets (title, category, current_probability, volume, close_date) VALUES
 ('Fed cuts rates again before year end', 'Economics', 0.58, 410000, '2026-12-31'),
 ('Bitcoin closes above $120k this year', 'Crypto', 0.33, 875000, '2026-12-31'),
 ('Incumbent party wins next general election', 'Politics', 0.49, 620000, '2028-11-07'),
 ('Reigning champion repeats as league winner', 'Sports', 0.27, 190000, '2026-06-15'),
 ('Next-gen console launches on schedule', 'Technology', 0.81, 95000, '2026-11-01'),
 ('Award-season frontrunner wins Best Picture', 'Entertainment', 0.44, 58000, '2027-03-10'),
 ('AI model surpasses human benchmark this year', 'Science', 0.22, 133000, '2026-12-31'),
 ('Hottest year on record confirmed', 'Climate', 0.71, 142000, '2026-12-31'),
 ('Major tech IPO prices above range', 'Business', 0.39, 84000, '2026-10-20'),
 ('Ceasefire holds through year end', 'World', 0.36, 205000, '2026-12-31'),
 ('Ethereum flips a top-3 market cap rank', 'Crypto', 0.19, 460000, '2026-12-31'),
 ('Unemployment rate falls below 3.8%', 'Economics', 0.31, 176000, '2026-12-31');

INSERT INTO analyses (market_id, verdict, summary, confidence) VALUES
 (1, 'fair', 'Probability roughly tracks current futures market pricing for a year-end cut.', 0.62),
 (2, 'overpriced', 'Volume-weighted momentum looks stretched relative to historical volatility bands.', 0.55),
 (3, 'fair', 'Close to a coin-flip, consistent with polling averages inside the margin of error.', 0.58),
 (4, 'underpriced', 'Squad strength metrics suggest better repeat odds than the market implies.', 0.51),
 (5, 'fair', 'Supply-chain signals are neutral; probability matches historical on-time launch rates.', 0.60),
 (6, 'overpriced', 'Frontrunner narrative may be pricing in critical buzz that award-body voting rarely rewards this strongly.', 0.47),
 (7, 'underpriced', 'Recent benchmark leaks suggest faster progress than the market has priced in.', 0.53),
 (8, 'fair', 'Tracks closely with current-year climate data trajectories.', 0.66),
 (9, 'overpriced', 'Comparable recent IPOs have priced within range more often than this estimate implies.', 0.49),
 (10, 'underpriced', 'Diplomatic backchannel activity suggests higher continuation odds than currently reflected.', 0.45);

INSERT INTO chat_messages (market_id, role, content) VALUES
 (1, 'user', 'Why is the Fed rate cut market sitting at 58%?'),
 (1, 'assistant', 'It reflects mixed signals from recent inflation prints and dovish commentary from committee members.'),
 (2, 'user', 'Is the Bitcoin $120k market overpriced?'),
 (2, 'assistant', 'Volume has spiked faster than historical volatility would suggest, which is a mild overpricing signal.'),
 (NULL, 'user', 'What markets have the widest gap between volume and confidence?'),
 (NULL, 'assistant', 'Crypto and entertainment markets currently show the largest volume-to-confidence gaps in this snapshot.'),
 (7, 'user', 'What is driving the AI benchmark market probability?'),
 (7, 'assistant', 'Recent published benchmark results are trending ahead of the market''s implied timeline.'),
 (9, 'user', 'Why do you think the IPO market is overpriced?'),
 (9, 'assistant', 'Comparable recent IPOs priced within range more often than this market currently implies.');
