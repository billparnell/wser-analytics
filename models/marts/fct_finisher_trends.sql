-- One row per race year, 1974-2025. The headline trend table.
--
-- Finisher counts are computed from stg_wser_results rather than taken from
-- wser.org's summary page: the two disagree for 1990 and 2005, and the results
-- list is the more trustworthy side (see tests/assert_finisher_counts_match_
-- wser_org.sql). Starter counts have no such alternative, so they come from the
-- summary and are null where it has no row.

with results as (

    select * from {{ ref('stg_wser_results') }}
    where is_official_finish

),

published as (

    select
        year as race_year,
        starters
    from {{ source('wser', 'wser_year_summary') }}

),

by_year as (

    select
        race_year,

        count(*)                                        as finishers,
        count(*) filter (where gender = 'F')            as female_finishers,
        count(*) filter (where gender = 'M')            as male_finishers,
        count(*) filter (where gender = 'NB')           as nonbinary_finishers,

        count(*) filter (where is_sub_24)               as sub_24_finishers,

        min(finish_seconds)                             as fastest_finish_seconds,
        median(finish_seconds)                          as median_finish_seconds,
        max(finish_seconds)                             as slowest_finish_seconds,

        avg(age)                                        as mean_age,
        median(age)                                     as median_age

    from results
    group by 1

)

select
    b.race_year,

    p.starters,
    b.finishers,
    p.starters - b.finishers                            as non_finishers,
    round(b.finishers::double / nullif(p.starters, 0), 4) as finish_rate,

    b.female_finishers,
    b.male_finishers,
    b.nonbinary_finishers,
    round(b.female_finishers::double / nullif(b.finishers, 0), 4) as female_share,

    b.sub_24_finishers,
    round(b.sub_24_finishers::double / nullif(b.finishers, 0), 4) as sub_24_rate,

    b.fastest_finish_seconds,
    b.median_finish_seconds,
    b.slowest_finish_seconds,

    b.mean_age,
    b.median_age

from by_year b
left join published p using (race_year)
