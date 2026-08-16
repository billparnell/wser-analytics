-- One row per runner per aid station reached, 2017-2025.
--
-- A runner only has a row where a split was recorded, so the last station
-- present is where their race ended. This is the grain Phase 5 validates the
-- pacing model against.

with source as (

    select * from {{ source('wser', 'splits') }}

),

renamed as (

    select
        runner_id,
        year            as race_year,
        station         as station_name,
        mile            as station_mile,
        elapsed_min     as elapsed_minutes

    from source

)

select * from renamed
