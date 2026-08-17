-- Course elevation profile sampled from the official GPX, one row per track
-- point in course order. Drives the dashboard's elevation silhouette.

with source as (

    select * from {{ source('wser', 'course_profile') }}

),

renamed as (

    select
        mile,
        elevation_ft,
        lat,
        lon

    from source

)

select * from renamed
