-- One row per runner across the whole 1974-2025 history. Multi-finish runners
-- are `where finish_count > 1`.
--
-- IDENTITY IS RESOLVED ON NAME ALONE. This is a deliberate simplification, and
-- it is wrong in both directions:
--
--   * A runner who changes surname splits into two careers. Meghan Arbogast
--     and Meghan Canfield are one person; the scrape carries her current name
--     for recent years and her earlier name for older ones.
--   * Two different people sharing a name merge into one career. Two Paul
--     Schmidts, aged 48 and 42, both finished in 2000 -- so that single career
--     row contains two humans and claims two finishes in one year.
--
-- Rather than hide that, `implied_birth_year_spread` measures it. A real
-- runner's race_year minus age should hold roughly constant across their
-- career (WSER is run in late June, so a birthday falling mid-year moves it by
-- at most one). A spread beyond two years means the row almost certainly mixes
-- people, and `has_identity_conflict` flags it. Treat flagged rows as suspect
-- in any "most finishes" ranking.

with results as (

    select * from {{ ref('stg_wser_results') }}
    where is_official_finish

),

keyed as (

    select
        lower(first_name) || ' ' || lower(last_name) as runner_key,
        *,
        race_year - age as implied_birth_year
    from results

)

select
    runner_key,
    max(runner_name)                            as runner_name,

    count(*)                                    as finish_count,
    count(distinct race_year)                   as distinct_years_finished,
    count(*) > 1                                as is_multi_finisher,

    min(race_year)                              as first_finish_year,
    max(race_year)                              as last_finish_year,
    max(race_year) - min(race_year)             as career_span_years,

    count(*) filter (where is_sub_24)           as sub_24_count,
    min(finish_seconds)                         as best_finish_seconds,
    median(finish_seconds)                      as median_finish_seconds,
    min(overall_place)                          as best_overall_place,

    min(age)                                    as youngest_age,
    max(age)                                    as oldest_age,

    -- Identity-quality signals; see the header.
    --
    -- Two finishes in one race year is proof rather than suspicion: nobody runs
    -- Western States twice in a June. Only Paul Schmidt trips it today, and the
    -- birth-year heuristic catches him too, but proof is worth encoding.
    count(*) > count(distinct race_year)        as finished_twice_in_one_year,
    max(implied_birth_year) - min(implied_birth_year) as implied_birth_year_spread,
    coalesce(
        max(implied_birth_year) - min(implied_birth_year) > 2, false
    ) or count(*) > count(distinct race_year)   as has_identity_conflict,
    count(distinct gender)                      as distinct_genders_reported

from keyed
group by 1
