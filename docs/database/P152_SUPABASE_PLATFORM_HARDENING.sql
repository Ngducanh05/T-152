-- ParkSmart AI — Supabase platform hardening
--
-- Preconditions:
-- 1. Alembic revision 20260819_0007 is already applied.
-- 2. public.profiles and all ParkSmart business tables exist.
--
-- Alembic remains authoritative for the public business schema.

begin;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'fk_profiles_auth_user_id'
          and conrelid = 'public.profiles'::regclass
    ) then
        alter table public.profiles
            add constraint fk_profiles_auth_user_id
            foreign key (id)
            references auth.users(id)
            on delete cascade;
    end if;
end
$$;

revoke all on table public.profiles from anon, authenticated;
revoke all on table public.parking_users from anon, authenticated;
revoke all on table public.vehicles from anon, authenticated;
revoke all on table public.map_nodes from anon, authenticated;
revoke all on table public.map_edges from anon, authenticated;
revoke all on table public.parking_slots from anon, authenticated;
revoke all on table public.parking_reservations from anon, authenticated;
revoke all on table public.parking_sessions from anon, authenticated;
revoke all on table public.parking_events from anon, authenticated;
revoke all on table public.wrong_parking_reports from anon, authenticated;

alter table public.profiles enable row level security;
alter table public.parking_users enable row level security;
alter table public.vehicles enable row level security;
alter table public.map_nodes enable row level security;
alter table public.map_edges enable row level security;
alter table public.parking_slots enable row level security;
alter table public.parking_reservations enable row level security;
alter table public.parking_sessions enable row level security;
alter table public.parking_events enable row level security;
alter table public.wrong_parking_reports enable row level security;

commit;
