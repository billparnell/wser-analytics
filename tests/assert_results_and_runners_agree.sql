-- The two ingest paths are independent: stg_wser_results is scraped from
-- wser.org, stg_wser_runners is parsed from the official splits spreadsheets.
-- Where they overlap (2017-2025) their finisher counts must agree exactly.
--
-- This is the test that catches spreadsheet-parsing regressions. It failed
-- before 2026-08-16 because prep_dashboard_data.py inferred finisher status
-- from the Time cell alone, silently demoting the two 2017 finishers whose
-- Time is blank (bibs 381 and 262) to DNFs.

with scraped as (

    select
        race_year,
        count(*) as finishers
    from {{ ref('stg_wser_results') }}
    where is_official_finish
    group by 1

),

spreadsheet as (

    select
        race_year,
        count(*) as finishers
    from {{ ref('stg_wser_runners') }}
    where is_finisher
    group by 1

)

select
    s.race_year,
    s.finishers as scraped_finishers,
    x.finishers as spreadsheet_finishers

from scraped s
inner join spreadsheet x using (race_year)
where s.finishers <> x.finishers
