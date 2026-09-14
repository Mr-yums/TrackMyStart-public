-- [Sol] Schéma figé du commit 1080ebac346f, avant coupons.

CREATE TABLE invoice_counters (
	year SERIAL NOT NULL,
	last_number INTEGER DEFAULT '0' NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (year)
)

;

CREATE TABLE login_attempts (
	id SERIAL NOT NULL,
	email VARCHAR(255) NOT NULL,
	ip_address VARCHAR(45) NOT NULL,
	failed_count INTEGER NOT NULL,
	last_failed_at TIMESTAMP WITH TIME ZONE,
	locked_until TIMESTAMP WITH TIME ZONE,
	PRIMARY KEY (id),
	CONSTRAINT uq_login_attempt UNIQUE (email, ip_address)
)

;
CREATE INDEX ix_login_attempts_email ON login_attempts (email);

CREATE TABLE users (
	id SERIAL NOT NULL,
	email VARCHAR(255) NOT NULL,
	password_hash VARCHAR(255) NOT NULL,
	display_name VARCHAR(80) NOT NULL,
	email_verified BOOLEAN NOT NULL,
	is_admin BOOLEAN NOT NULL,
	is_active BOOLEAN NOT NULL,
	last_login_at TIMESTAMP WITH TIME ZONE,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id)
)

;
CREATE UNIQUE INDEX ix_users_email ON users (email);

CREATE TABLE follows (
	id SERIAL NOT NULL,
	user_id INTEGER NOT NULL,
	person_id INTEGER NOT NULL,
	name VARCHAR(255) NOT NULL,
	profile_path VARCHAR(255),
	department VARCHAR(80),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_follow_user_person UNIQUE (user_id, person_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_follows_user_id ON follows (user_id);

CREATE TABLE payments (
	id SERIAL NOT NULL,
	user_id INTEGER NOT NULL,
	order_id VARCHAR(64) NOT NULL,
	provider VARCHAR(20) NOT NULL,
	provider_payment_id VARCHAR(128),
	provider_customer_id VARCHAR(128),
	status VARCHAR(20) NOT NULL,
	amount_cents INTEGER NOT NULL,
	currency VARCHAR(3) NOT NULL,
	description VARCHAR(255) NOT NULL,
	receipt_url VARCHAR(512),
	card_brand VARCHAR(40),
	card_last4 VARCHAR(4),
	error_message TEXT,
	raw JSON,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	UNIQUE (order_id)
)

;
CREATE INDEX ix_payments_provider_payment_id ON payments (provider_payment_id);
CREATE INDEX ix_payments_user_id ON payments (user_id);

CREATE TABLE user_preferences (
	user_id INTEGER NOT NULL,
	settings JSON NOT NULL,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (user_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

;

CREATE TABLE watchlist (
	id SERIAL NOT NULL,
	user_id INTEGER NOT NULL,
	media_type VARCHAR(10) NOT NULL,
	media_id VARCHAR(64) NOT NULL,
	title VARCHAR(255) NOT NULL,
	poster VARCHAR(512),
	year VARCHAR(8),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_watchlist_item UNIQUE (user_id, media_type, media_id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_watchlist_user_id ON watchlist (user_id);

CREATE TABLE invoices (
	id SERIAL NOT NULL,
	number VARCHAR(32) NOT NULL,
	user_id INTEGER NOT NULL,
	payment_id INTEGER NOT NULL,
	description VARCHAR(255) NOT NULL,
	amount_ht_cents INTEGER NOT NULL,
	vat_cents INTEGER NOT NULL,
	amount_ttc_cents INTEGER NOT NULL,
	currency VARCHAR(3) NOT NULL,
	issued_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (number),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	UNIQUE (payment_id),
	FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE CASCADE
)

;
CREATE INDEX ix_invoices_user_id ON invoices (user_id);

CREATE TABLE subscriptions (
	id SERIAL NOT NULL,
	user_id INTEGER NOT NULL,
	plan VARCHAR(20) NOT NULL,
	status VARCHAR(20) NOT NULL,
	started_at TIMESTAMP WITH TIME ZONE NOT NULL,
	current_period_end TIMESTAMP WITH TIME ZONE NOT NULL,
	canceled_at TIMESTAMP WITH TIME ZONE,
	payment_id INTEGER,
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
	FOREIGN KEY(payment_id) REFERENCES payments (id) ON DELETE SET NULL
)

;
CREATE INDEX ix_subscriptions_user_id ON subscriptions (user_id);

CREATE TABLE invoice_snapshots (
	invoice_id INTEGER NOT NULL,
	details JSON NOT NULL,
	PRIMARY KEY (invoice_id),
	FOREIGN KEY(invoice_id) REFERENCES invoices (id) ON DELETE CASCADE
)

;
