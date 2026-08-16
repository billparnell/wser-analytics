-- One row per starter, 2017-2025, from the official splits spreadsheets.
--
-- The spreadsheet lists every starter in one ordered block -- finishers ranked
-- from 1, then DNFs continuing the same numbering -- so its "Overall Place" is
-- a row ordinal rather than a finisher flag. scripts/prep_dashboard_data.py
-- resolves that; see the comment there. Finisher counts here reconcile exactly
-- with wser.org for all eight years.

with source as (

    select * from {{ source('wser', 'runners') }}

),

renamed as (

    select
        runner_id,
        year                            as race_year,
        bib,

        trim(first_name)                as first_name,
        trim(last_name)                 as last_name,
        trim(name)                      as runner_name,

        gender                          as gender_reported,
        case
            when trim(gender) like 'NB%' then 'NB'
            when trim(gender) like 'M%'  then 'M'
            when trim(gender) like 'F%'  then 'F'
        end                             as gender,

        cast(age as integer)            as age,
        nullif(trim(city), '')          as city,
        nullif(trim(state), '')         as state,
        nullif(trim(country), '')       as country,

        finished                        as is_finisher,
        cast(overall_place as integer)  as overall_place,
        cast(gender_place as integer)   as gender_place,

        -- Null for two 2017 finishers whose Time cell is blank in the
        -- spreadsheet; they are still finishers and still placed.
        finish_min                      as finish_minutes,
        finished and finish_min < 24 * 60 as is_sub_24

    from source

)

select * from renamed
