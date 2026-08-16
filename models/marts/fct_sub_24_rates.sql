-- Sub-24 (silver buckle) rates, one row per race year per gender.
--
-- Counts *people*, not places. Where a tie straddles the 24-hour line both
-- runners are counted, so 1983 and 1984 each come out one higher than
-- wser.org's summary page, which appears to count places. Counting humans who
-- broke 24 hours is the defensible reading; the difference is documented rather
-- than tuned away.

with results as (

    select * from {{ ref('stg_wser_results') }}
    where is_official_finish

)

select
    race_year,
    gender,

    count(*)                                as finishers,
    count(*) filter (where is_sub_24)       as sub_24_finishers,
    round(
        count(*) filter (where is_sub_24)::double / nullif(count(*), 0), 4
    )                                       as sub_24_rate,

    min(finish_seconds)                     as fastest_finish_seconds,
    median(finish_seconds)                  as median_finish_seconds

from results
group by 1, 2
