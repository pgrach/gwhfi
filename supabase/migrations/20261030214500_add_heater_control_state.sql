-- Durable state and audit evidence for the thermostat-cycle controller.
-- These tables are intentionally service-only. Browser dashboards can expose
-- derived summaries later without publishing raw household control decisions.

create table if not exists public.heater_control_state (
    site_id text not null,
    heater_key text not null,
    mode text not null default 'idle',
    policy_version integer not null default 1,
    shadow_mode boolean not null default true,
    hold_until timestamptz,
    tank_satisfied_at timestamptz,
    heat_session_started_at timestamptz,
    last_sustained_heat_at timestamptz,
    last_transition_at timestamptz,
    session_energy_wh double precision not null default 0,
    state_payload jsonb not null default '{}'::jsonb,
    evidence jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (site_id, heater_key),
    constraint heater_control_state_site_nonempty_check
        check (length(btrim(site_id)) > 0),
    constraint heater_control_state_key_nonempty_check
        check (length(btrim(heater_key)) > 0),
    constraint heater_control_state_mode_check
        check (mode in ('idle', 'heating', 'holding', 'probing', 'fault')),
    constraint heater_control_state_policy_version_check
        check (policy_version >= 1),
    constraint heater_control_state_session_energy_check
        check (session_energy_wh >= 0 and session_energy_wh <= 1000000000),
    constraint heater_control_state_payload_object_check
        check (jsonb_typeof(state_payload) = 'object'),
    constraint heater_control_state_evidence_object_check
        check (jsonb_typeof(evidence) = 'object')
);

comment on table public.heater_control_state is
    'Latest durable thermostat-cycle inference state per site and heater; owned by the Railway controller.';
comment on column public.heater_control_state.state_payload is
    'Versioned rolling detector samples and counters required to resume safely after a controller restart.';
comment on column public.heater_control_state.evidence is
    'Summary evidence for the latest state transition and operator diagnosis.';

create index if not exists heater_control_state_hold_until_idx
    on public.heater_control_state (hold_until)
    where hold_until is not null;

create table if not exists public.heater_control_events (
    event_id text primary key,
    site_id text not null,
    heater_key text not null,
    occurred_at timestamptz not null,
    event_type text not null,
    mode_before text,
    mode_after text,
    policy_version integer not null default 1,
    shadow_mode boolean not null default true,
    relay_commanded_on boolean,
    observed_power_w double precision,
    session_energy_wh double precision,
    scheduled_slot_start timestamptz,
    scheduled_slot_end timestamptz,
    evidence jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    constraint heater_control_events_id_nonempty_check
        check (length(btrim(event_id)) > 0),
    constraint heater_control_events_site_nonempty_check
        check (length(btrim(site_id)) > 0),
    constraint heater_control_events_key_nonempty_check
        check (length(btrim(heater_key)) > 0),
    constraint heater_control_events_type_nonempty_check
        check (length(btrim(event_type)) > 0),
    constraint heater_control_events_mode_before_check
        check (mode_before is null or mode_before in ('idle', 'heating', 'holding', 'probing', 'fault')),
    constraint heater_control_events_mode_after_check
        check (mode_after is null or mode_after in ('idle', 'heating', 'holding', 'probing', 'fault')),
    constraint heater_control_events_policy_version_check
        check (policy_version >= 1),
    constraint heater_control_events_power_check
        check (observed_power_w is null or (observed_power_w >= 0 and observed_power_w <= 100000)),
    constraint heater_control_events_energy_check
        check (session_energy_wh is null or (session_energy_wh >= 0 and session_energy_wh <= 1000000000)),
    constraint heater_control_events_slot_order_check
        check (
            scheduled_slot_start is null
            or scheduled_slot_end is null
            or scheduled_slot_end > scheduled_slot_start
        ),
    constraint heater_control_events_evidence_object_check
        check (jsonb_typeof(evidence) = 'object')
);

comment on table public.heater_control_events is
    'Append-only evidence and decisions from thermostat-cycle detection, including shadow-mode decisions.';
comment on column public.heater_control_events.event_id is
    'Controller-generated idempotency key so retried event writes cannot duplicate training evidence.';

create index if not exists heater_control_events_site_heater_time_idx
    on public.heater_control_events (site_id, heater_key, occurred_at desc);

create index if not exists heater_control_events_type_time_idx
    on public.heater_control_events (event_type, occurred_at desc);

alter table public.heater_control_state enable row level security;
alter table public.heater_control_events enable row level security;

revoke all privileges on table public.heater_control_state from public, anon, authenticated;
revoke all privileges on table public.heater_control_events from public, anon, authenticated;

grant select, insert, update on table public.heater_control_state to service_role;
grant select, insert on table public.heater_control_events to service_role;

drop policy if exists heater_control_state_service_role_all on public.heater_control_state;
create policy heater_control_state_service_role_all
    on public.heater_control_state
    for all
    to service_role
    using (true)
    with check (true);

drop policy if exists heater_control_events_service_role_insert on public.heater_control_events;
create policy heater_control_events_service_role_insert
    on public.heater_control_events
    for insert
    to service_role
    with check (true);

drop policy if exists heater_control_events_service_role_select on public.heater_control_events;
create policy heater_control_events_service_role_select
    on public.heater_control_events
    for select
    to service_role
    using (true);

