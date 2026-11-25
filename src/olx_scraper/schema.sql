create table runs (
    id          integer primary key,
    category    text not null,
    pages_asked integer not null check (pages_asked > 0),
    ad_limit    integer check (ad_limit > 0),
    pages_read  integer not null default 0,
    site_pages  integer,
    status      text not null default 'running' check (status in ('running', 'done', 'failed')),
    reason      text,
    started_at  text not null,
    ended_at    text,
    check ((status = 'running') = (ended_at is null)),
    check ((status = 'failed') = (reason is not null))
) strict;

-- One row per listing per run, so history is never overwritten.
create table observations (
    run_id       integer not null references runs (id),
    listing_id   integer not null,
    seen_at      text not null,
    page         integer not null,
    position     integer not null,
    promoted     integer not null check (promoted in (0, 1)),
    url          text not null,
    title        text not null,
    deal_type    text,
    region       text,
    city         text,
    district     text,
    rooms        integer,
    floor        integer,
    total_floors integer,
    area_m2      real,
    posted_at    text,
    price_kind   text check (price_kind in ('fixed', 'free', 'exchange')),
    price_cents  integer check (price_cents >= 0),
    currency     text check (currency in ('UAH', 'USD', 'EUR')),
    primary key (run_id, listing_id),
    check ((price_kind is 'fixed') = (price_cents is not null)),
    check ((price_cents is null) = (currency is null))
) strict;

create index observations_by_listing on observations (listing_id, seen_at);

-- Every listing whose price could not be read, and why.
create table gaps (
    run_id     integer not null,
    listing_id integer not null,
    reason     text not null,
    primary key (run_id, listing_id),
    foreign key (run_id, listing_id) references observations (run_id, listing_id)
) strict;

-- Compares each listing's last two sightings rather than two runs: a listing that drops out of
-- search for a few days and comes back still yields its change. A currency switch is not a
-- price change.
create view price_changes as
with sightings as (
    select listing_id, url, title, city, seen_at, price_cents, currency,
           lag(seen_at)     over sighting as prev_seen_at,
           lag(price_cents) over sighting as prev_cents,
           lag(currency)    over sighting as prev_currency
    from observations
    where price_kind = 'fixed'
    window sighting as (partition by listing_id order by seen_at, run_id)
)
select listing_id, url, title, city, currency,
       prev_cents / 100.0  as price_before,
       price_cents / 100.0 as price_after,
       round(100.0 * (price_cents - prev_cents) / nullif(prev_cents, 0), 1) as change_pct,
       prev_seen_at, seen_at
from sightings
where currency = prev_currency and price_cents <> prev_cents;
