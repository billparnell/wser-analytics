-- One row per race year, age group and gender.
--
-- The bands are ten-year decades of our own choosing, not WSER's official award
-- divisions -- don't read these as division results. Age is missing for 14
-- finishers across the whole history; they fall into the 'Unknown' band rather
-- than being dropped, so the bands still sum to the year's finisher count.

with results as (

    select * from {{ ref('stg_wser_results') }}
    where is_official_finish

),

banded as (

    select
        *,
        case
            when age is null then 'Unknown'
            when age < 30     then 'Under 30'
            when age < 40     then '30-39'
            when age < 50     then '40-49'
            when age < 60     then '50-59'
            when age < 70     then '60-69'
            else                   '70+'
        end as age_group,
        case
            when age is null then 99
            when age < 30     then 1
            when age < 40     then 2
            when age < 50     then 3
            when age < 60     then 4
            when age < 70     then 5
            else                   6
        end as age_group_order
    from results

)

select
    race_year,
    age_group,
    age_group_order,
    gender,

    count(*)                                as finishers,
    count(*) filter (where is_sub_24)       as sub_24_finishers,
    round(
        count(*) filter (where is_sub_24)::double / nullif(count(*), 0), 4
    )                                       as sub_24_rate,

    min(finish_seconds)                     as fastest_finish_seconds,
    median(finish_seconds)                  as median_finish_seconds,
    min(overall_place)                      as best_overall_place

from banded
group by 1, 2, 3, 4
