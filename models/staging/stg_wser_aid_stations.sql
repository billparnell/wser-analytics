-- The 24 aid stations, in course order. Elevation is read off the official GPX
-- by scripts/prep_dashboard_data.py; Escarpment has no GPX waypoint and is
-- interpolated from the profile.

with source as (

    select * from {{ source('wser', 'aid_stations') }}

),

renamed as (

    select
        station         as station_name,
        mile            as station_mile,
        cutoff_hours,
        elevation_ft,
        row_number() over (order by mile) as station_order

    from source

)

select * from renamed
