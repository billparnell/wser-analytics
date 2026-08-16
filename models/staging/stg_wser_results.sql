-- Scraped finisher results, 1974-2025: one row per finisher per year.
--
-- No natural key exists in the source. Ties share an official place, so
-- (year, place) repeats 203 times; two different Paul Schmidts (ages 48 and 42)
-- both finished in 2000, so (year, name) repeats once. Adding finish_minutes
-- makes it unique across all 11,046 rows.

with source as (

    select * from {{ source('wser', 'wser_results') }}

),

renamed as (

    select
        md5(concat_ws(
            '|', year, first_name, last_name, finish_minutes
        )) as result_id,

        year                                    as race_year,
        cast(place as integer)                  as overall_place,
        trim(first_name)                        as first_name,
        trim(last_name)                         as last_name,
        trim(first_name) || ' ' || trim(last_name) as runner_name,

        -- Five reported values: M, F, and three non-binary spellings with
        -- inconsistent spacing ('NB (M)', ' NB(F)', ' M (X)'). Keep the raw
        -- string; normalise on the leading token.
        gender                                  as gender_reported,
        case
            when trim(gender) like 'NB%' then 'NB'
            when trim(gender) like 'M%'  then 'M'
            when trim(gender) like 'F%'  then 'F'
        end                                     as gender,

        cast(age as integer)                    as age,
        nullif(trim(state), '')                 as state,

        finish_time                             as finish_time,

        -- Hours run past 24 (the cutoff is 30), so this cannot be a TIME.
        -- finish_minutes is the scrape's own value, truncated to the minute;
        -- finish_seconds is parsed from the string and keeps the seconds.
          cast(split_part(finish_time, ':', 1) as integer) * 3600
        + cast(split_part(finish_time, ':', 2) as integer) * 60
        + coalesce(try_cast(split_part(finish_time, ':', 3) as integer), 0)
                                                as finish_seconds,
        finish_minutes                          as finish_minutes_truncated,

        -- Runners recorded past the 30-hour cutoff appear with no place.
        place is not null                       as is_official_finish,
        cast(place as integer) is not null
            and finish_minutes < 24 * 60        as is_sub_24

    from source

)

select * from renamed
