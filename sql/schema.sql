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
  status TEXT,
  raw_result TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
