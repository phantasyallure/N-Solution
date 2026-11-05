-- Nardjis Solutions - Supabase schema.
-- Run once: Supabase dashboard -> SQL Editor -> New query -> paste -> Run.

create table if not exists nj_restaurants (
  id          text primary key,
  name        text not null,
  created_at  timestamptz not null default now()
);

-- one row per restaurant = its latest snapshot (overwritten every ~2 s by the engine)
create table if not exists nj_state (
  restaurant_id text primary key references nj_restaurants(id) on delete cascade,
  state         jsonb not null,      -- full snapshot (room, tables, team, waits, events)
  summary       jsonb not null,      -- small card for the home screen
  updated_at    timestamptz not null default now()
);

-- history (alerts, waits, cleaning) - used by the daily report
create table if not exists nj_events (
  id            bigserial primary key,
  restaurant_id text not null references nj_restaurants(id) on delete cascade,
  ts            timestamptz not null default now(),
  type          text not null,
  table_name    text,
  staff         text,
  seconds       real,
  notify        text
);
create index if not exists nj_events_rest_ts on nj_events (restaurant_id, ts desc);

-- updated_at is set by the database, so "online/offline" does not depend on the engine computer's clock
create or replace function nj_touch() returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;
drop trigger if exists nj_state_touch on nj_state;
create trigger nj_state_touch before update on nj_state for each row execute function nj_touch();

-- Lock the tables: nobody can read or write them with the public (anon) key.
-- Only the secret/service key (engine computer + Vercel functions) can, because it bypasses RLS.
alter table nj_restaurants enable row level security;
alter table nj_state       enable row level security;
alter table nj_events      enable row level security;

-- optional: keep the history table small (delete events older than 90 days)
-- delete from nj_events where ts < now() - interval '90 days';
