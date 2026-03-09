CREATE TABLE IF NOT EXISTS post_metrics_daily (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  stat_date TEXT NOT NULL,
  post_id TEXT NOT NULL,
  title TEXT,
  exposure INTEGER DEFAULT 0,
  views INTEGER DEFAULT 0,
  likes INTEGER DEFAULT 0,
  comments INTEGER DEFAULT 0,
  collects INTEGER DEFAULT 0,
  shares INTEGER DEFAULT 0,
  profile_visits INTEGER DEFAULT 0,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS candidate_posts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_date TEXT NOT NULL,
  candidate_no INTEGER NOT NULL,
  experiment_run_id INTEGER,
  arm_key TEXT,
  generation_mode TEXT,
  bandit_sample REAL,
  topic TEXT,
  title TEXT,
  content TEXT,
  tags TEXT,
  status TEXT DEFAULT 'generated',
  score REAL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS publish_records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  publish_date TEXT NOT NULL,
  candidate_id INTEGER,
  publish_mode TEXT,
  note_link TEXT,
  note_id TEXT,
  status TEXT,
  raw_result TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS experiment_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_date TEXT NOT NULL,
  topic TEXT,
  account TEXT,
  selection_policy TEXT NOT NULL,
  status TEXT DEFAULT 'generated',
  selected_candidate_no INTEGER,
  metadata_json TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS experiment_arms (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL,
  candidate_no INTEGER NOT NULL,
  arm_key TEXT,
  topic TEXT,
  title TEXT,
  content TEXT,
  tags TEXT,
  hook_type TEXT,
  structure_type TEXT,
  cta_type TEXT,
  features_json TEXT,
  score REAL,
  status TEXT DEFAULT 'generated',
  publish_record_id INTEGER,
  result_label TEXT,
  engagement_rate REAL,
  reward_source TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (run_id) REFERENCES experiment_runs(id)
);

CREATE TABLE IF NOT EXISTS policy_arm_stats (
  topic TEXT NOT NULL,
  arm_key TEXT NOT NULL,
  alpha REAL NOT NULL DEFAULT 1.0,
  beta REAL NOT NULL DEFAULT 1.0,
  pulls INTEGER NOT NULL DEFAULT 0,
  wins INTEGER NOT NULL DEFAULT 0,
  last_reward REAL,
  updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (topic, arm_key)
);

CREATE TABLE IF NOT EXISTS policy_reward_events (
  arm_id INTEGER PRIMARY KEY,
  topic TEXT NOT NULL,
  arm_key TEXT NOT NULL,
  reward REAL NOT NULL,
  label TEXT NOT NULL,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
