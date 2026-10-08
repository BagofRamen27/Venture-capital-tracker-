CREATE TABLE app_settings (
	"key" VARCHAR(80) NOT NULL, 
	value JSON NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY ("key")
);


CREATE TABLE investors (
	id INTEGER NOT NULL, 
	name VARCHAR(255) NOT NULL, 
	normalized_name VARCHAR(255) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (normalized_name)
);


CREATE TABLE job_locks (
	name VARCHAR(80) NOT NULL, 
	acquired_at DATETIME NOT NULL, 
	expires_at DATETIME NOT NULL, 
	PRIMARY KEY (name)
);


CREATE TABLE job_runs (
	id INTEGER NOT NULL, 
	job_name VARCHAR(80) NOT NULL, 
	source_key VARCHAR(80), 
	"trigger" VARCHAR(20) NOT NULL, 
	started_at DATETIME NOT NULL, 
	finished_at DATETIME, 
	status VARCHAR(20) NOT NULL, 
	items_fetched INTEGER NOT NULL, 
	items_new INTEGER NOT NULL, 
	items_duplicate INTEGER NOT NULL, 
	startups_created INTEGER NOT NULL, 
	error_message TEXT, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_job_runs_job_name ON job_runs (job_name);
CREATE INDEX ix_job_runs_source_key ON job_runs (source_key);

CREATE TABLE news_articles (
	id INTEGER NOT NULL, 
	source_key VARCHAR(80) NOT NULL, 
	source_type VARCHAR(40) NOT NULL, 
	publisher VARCHAR(120), 
	url VARCHAR(1000) NOT NULL, 
	title TEXT NOT NULL, 
	summary TEXT, 
	published_at DATETIME, 
	retrieved_at DATETIME NOT NULL, 
	title_fingerprint VARCHAR(64) NOT NULL, 
	duplicate_of_id INTEGER, 
	event_types JSON, 
	sentiment VARCHAR(20), 
	sentiment_score FLOAT, 
	classification_evidence JSON, 
	community_metrics JSON, 
	PRIMARY KEY (id), 
	UNIQUE (url), 
	FOREIGN KEY(duplicate_of_id) REFERENCES news_articles (id)
);

CREATE INDEX ix_news_articles_title_fingerprint ON news_articles (title_fingerprint);
CREATE INDEX ix_news_articles_source_key ON news_articles (source_key);
CREATE INDEX ix_news_articles_published_at ON news_articles (published_at);

CREATE TABLE startups (
	id INTEGER NOT NULL, 
	external_id VARCHAR(64), 
	name VARCHAR(255) NOT NULL, 
	normalized_name VARCHAR(255) NOT NULL, 
	legal_name VARCHAR(255), 
	website VARCHAR(500), 
	domain VARCHAR(255), 
	industry VARCHAR(120), 
	sub_industry VARCHAR(255), 
	description TEXT, 
	hq_city VARCHAR(120), 
	hq_state VARCHAR(120), 
	hq_country VARCHAR(120), 
	founded_year INTEGER, 
	funding_stage VARCHAR(60), 
	business_model VARCHAR(255), 
	founders TEXT, 
	key_people TEXT, 
	total_funding_amount FLOAT, 
	total_funding_currency VARCHAR(8), 
	total_funding_basis TEXT, 
	latest_funding_amount FLOAT, 
	latest_funding_currency VARCHAR(8), 
	latest_funding_date DATE, 
	latest_funding_status VARCHAR(40), 
	valuation_amount FLOAT, 
	valuation_currency VARCHAR(8), 
	valuation_basis TEXT, 
	revenue_amount FLOAT, 
	revenue_basis TEXT, 
	growth_signals TEXT, 
	latest_news_title TEXT, 
	latest_news_url VARCHAR(1000), 
	latest_news_date DATETIME, 
	primary_source_url VARCHAR(1000), 
	sec_cik VARCHAR(20), 
	review_status VARCHAR(40) NOT NULL, 
	confidence_score FLOAT, 
	confidence_label VARCHAR(20), 
	confidence_breakdown JSON, 
	flags JSON, 
	is_demo BOOLEAN NOT NULL, 
	extra JSON, 
	discovered_via VARCHAR(80), 
	first_discovered_at DATETIME NOT NULL, 
	last_updated_at DATETIME NOT NULL, 
	last_verified_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (external_id)
);

CREATE INDEX ix_startups_domain ON startups (domain);
CREATE INDEX ix_startups_sec_cik ON startups (sec_cik);
CREATE INDEX ix_startups_funding_stage ON startups (funding_stage);
CREATE INDEX ix_startups_review_status ON startups (review_status);
CREATE INDEX ix_startups_industry ON startups (industry);
CREATE INDEX ix_startups_first_discovered_at ON startups (first_discovered_at);
CREATE INDEX ix_startups_normalized_name ON startups (normalized_name);

CREATE TABLE article_mentions (
	id INTEGER NOT NULL, 
	article_id INTEGER NOT NULL, 
	startup_id INTEGER NOT NULL, 
	match_method VARCHAR(40) NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (article_id, startup_id), 
	FOREIGN KEY(article_id) REFERENCES news_articles (id) ON DELETE CASCADE, 
	FOREIGN KEY(startup_id) REFERENCES startups (id) ON DELETE CASCADE
);

CREATE INDEX ix_article_mentions_startup_id ON article_mentions (startup_id);

CREATE TABLE duplicate_candidates (
	id INTEGER NOT NULL, 
	startup_a_id INTEGER NOT NULL, 
	startup_b_id INTEGER NOT NULL, 
	similarity FLOAT NOT NULL, 
	reason TEXT NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	resolved_at DATETIME, 
	PRIMARY KEY (id), 
	UNIQUE (startup_a_id, startup_b_id), 
	FOREIGN KEY(startup_a_id) REFERENCES startups (id) ON DELETE CASCADE, 
	FOREIGN KEY(startup_b_id) REFERENCES startups (id) ON DELETE CASCADE
);


CREATE TABLE investment_scores (
	id INTEGER NOT NULL, 
	startup_id INTEGER NOT NULL, 
	computed_at DATETIME NOT NULL, 
	is_current BOOLEAN NOT NULL, 
	total_score FLOAT, 
	rating VARCHAR(40) NOT NULL, 
	coverage FLOAT NOT NULL, 
	weights JSON NOT NULL, 
	factors JSON NOT NULL, 
	missing JSON NOT NULL, 
	thesis TEXT, 
	risks JSON, 
	model_version VARCHAR(20) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(startup_id) REFERENCES startups (id) ON DELETE CASCADE
);

CREATE INDEX ix_investment_scores_is_current ON investment_scores (is_current);
CREATE INDEX ix_investment_scores_startup_id ON investment_scores (startup_id);

CREATE TABLE review_events (
	id INTEGER NOT NULL, 
	startup_id INTEGER NOT NULL, 
	from_status VARCHAR(40), 
	to_status VARCHAR(40) NOT NULL, 
	note TEXT, 
	actor VARCHAR(120), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(startup_id) REFERENCES startups (id) ON DELETE CASCADE
);

CREATE INDEX ix_review_events_startup_id ON review_events (startup_id);

CREATE TABLE score_overrides (
	id INTEGER NOT NULL, 
	startup_id INTEGER NOT NULL, 
	factor VARCHAR(40) NOT NULL, 
	score FLOAT NOT NULL, 
	note TEXT NOT NULL, 
	analyst VARCHAR(120), 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (startup_id, factor), 
	FOREIGN KEY(startup_id) REFERENCES startups (id) ON DELETE CASCADE
);


CREATE TABLE sec_filings (
	id INTEGER NOT NULL, 
	accession_number VARCHAR(30) NOT NULL, 
	cik VARCHAR(20) NOT NULL, 
	form_type VARCHAR(10) NOT NULL, 
	is_amendment BOOLEAN NOT NULL, 
	issuer_name VARCHAR(255) NOT NULL, 
	normalized_name VARCHAR(255) NOT NULL, 
	filing_date DATE, 
	entity_type VARCHAR(80), 
	year_of_incorporation INTEGER, 
	incorporated_within_five_years BOOLEAN, 
	industry_group VARCHAR(120), 
	investment_fund_type VARCHAR(120), 
	revenue_range VARCHAR(80), 
	federal_exemptions JSON, 
	date_of_first_sale DATE, 
	total_offering_amount FLOAT, 
	offering_amount_indefinite BOOLEAN NOT NULL, 
	total_amount_sold FLOAT, 
	total_remaining FLOAT, 
	investor_count INTEGER, 
	has_non_accredited_investors BOOLEAN, 
	securities_types JSON, 
	related_persons JSON, 
	city VARCHAR(120), 
	state_or_country VARCHAR(80), 
	filing_url VARCHAR(1000) NOT NULL, 
	document_url VARCHAR(1000), 
	retrieved_at DATETIME NOT NULL, 
	is_startup_candidate BOOLEAN NOT NULL, 
	candidate_reason TEXT, 
	startup_id INTEGER, 
	suggested_startup_id INTEGER, 
	match_status VARCHAR(30) NOT NULL, 
	match_score FLOAT, 
	match_note TEXT, 
	review_flags JSON, 
	PRIMARY KEY (id), 
	UNIQUE (accession_number), 
	FOREIGN KEY(startup_id) REFERENCES startups (id) ON DELETE SET NULL, 
	FOREIGN KEY(suggested_startup_id) REFERENCES startups (id) ON DELETE SET NULL
);

CREATE INDEX ix_sec_filings_startup_id ON sec_filings (startup_id);
CREATE INDEX ix_sec_filings_normalized_name ON sec_filings (normalized_name);
CREATE INDEX ix_sec_filings_filing_date ON sec_filings (filing_date);
CREATE INDEX ix_sec_filings_cik ON sec_filings (cik);

CREATE TABLE citations (
	id INTEGER NOT NULL, 
	startup_id INTEGER NOT NULL, 
	field_name VARCHAR(80) NOT NULL, 
	value_text TEXT, 
	evidence_status VARCHAR(40) NOT NULL, 
	is_estimate BOOLEAN NOT NULL, 
	source_type VARCHAR(40), 
	publisher VARCHAR(120), 
	source_url VARCHAR(1000), 
	article_id INTEGER, 
	sec_filing_id INTEGER, 
	published_at DATETIME, 
	retrieved_at DATETIME NOT NULL, 
	note TEXT, 
	dedupe_key VARCHAR(255) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(startup_id) REFERENCES startups (id) ON DELETE CASCADE, 
	FOREIGN KEY(article_id) REFERENCES news_articles (id) ON DELETE SET NULL, 
	FOREIGN KEY(sec_filing_id) REFERENCES sec_filings (id) ON DELETE SET NULL, 
	UNIQUE (dedupe_key)
);

CREATE INDEX ix_citations_startup_id ON citations (startup_id);

CREATE TABLE discovery_signals (
	id INTEGER NOT NULL, 
	startup_id INTEGER NOT NULL, 
	signal_type VARCHAR(60) NOT NULL, 
	source_key VARCHAR(80) NOT NULL, 
	article_id INTEGER, 
	sec_filing_id INTEGER, 
	detail TEXT, 
	source_url VARCHAR(1000), 
	observed_at DATETIME, 
	detected_at DATETIME NOT NULL, 
	dedupe_key VARCHAR(255) NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(startup_id) REFERENCES startups (id) ON DELETE CASCADE, 
	FOREIGN KEY(article_id) REFERENCES news_articles (id) ON DELETE SET NULL, 
	FOREIGN KEY(sec_filing_id) REFERENCES sec_filings (id) ON DELETE SET NULL, 
	UNIQUE (dedupe_key)
);

CREATE INDEX ix_discovery_signals_startup_id ON discovery_signals (startup_id);
CREATE INDEX ix_discovery_signals_signal_type ON discovery_signals (signal_type);

CREATE TABLE funding_rounds (
	id INTEGER NOT NULL, 
	startup_id INTEGER NOT NULL, 
	round_type VARCHAR(60), 
	amount FLOAT, 
	currency VARCHAR(8), 
	amount_text VARCHAR(120), 
	announced_date DATE, 
	evidence_status VARCHAR(40) NOT NULL, 
	source_url VARCHAR(1000), 
	article_id INTEGER, 
	sec_filing_id INTEGER, 
	publishers JSON, 
	"conflict" BOOLEAN NOT NULL, 
	conflict_note TEXT, 
	notes TEXT, 
	extra JSON, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(startup_id) REFERENCES startups (id) ON DELETE CASCADE, 
	FOREIGN KEY(article_id) REFERENCES news_articles (id) ON DELETE SET NULL, 
	FOREIGN KEY(sec_filing_id) REFERENCES sec_filings (id) ON DELETE SET NULL
);

CREATE INDEX ix_funding_rounds_startup_id ON funding_rounds (startup_id);

CREATE TABLE round_investors (
	id INTEGER NOT NULL, 
	round_id INTEGER NOT NULL, 
	investor_id INTEGER NOT NULL, 
	is_lead BOOLEAN NOT NULL, 
	source_url VARCHAR(1000), 
	PRIMARY KEY (id), 
	UNIQUE (round_id, investor_id), 
	FOREIGN KEY(round_id) REFERENCES funding_rounds (id) ON DELETE CASCADE, 
	FOREIGN KEY(investor_id) REFERENCES investors (id) ON DELETE CASCADE
);


