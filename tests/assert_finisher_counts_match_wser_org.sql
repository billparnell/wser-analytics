-- Official finisher counts should match wser.org's own per-year summary.
--
-- Two known upstream discrepancies are excluded. Both are disagreements
-- between two separately scraped wser.org pages, not modelling errors:
--
--   1990 -- results list has 211 official finishers, summary says 208. The
--           1990 list is itself odd: place 21 is missing and one place is
--           shared, so it is 211 rows over 210 distinct places.
--   2005 -- results list has 318 finishers over a clean, gapless 1-318 place
--           sequence; the summary says 317. The summary is the suspect side.
--
-- Resolving these means going back to wser.org, not changing the model. Until
-- then they are pinned here so any *new* divergence still fails the build.

with modelled as (

    select
        race_year,
        count(*) as finishers
    from {{ ref('stg_wser_results') }}
    where is_official_finish
    group by 1

),

published as (

    select
        year as race_year,
        finishers
    from {{ source('wser', 'wser_year_summary') }}

)

select
    m.race_year,
    m.finishers as modelled_finishers,
    p.finishers as published_finishers

from modelled m
inner join published p using (race_year)
where m.finishers <> p.finishers
  and m.race_year not in (1990, 2005)
