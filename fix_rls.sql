-- Run this script in the Supabase SQL Editor to resolve the "RLS Disabled" warning.

-- 1. Enable Row Level Security
ALTER TABLE public.energy_readings ENABLE ROW LEVEL SECURITY;

-- 2. Create a policy for READ access (Public)
-- Allows the frontend dashboard (anon role) to view the data
CREATE POLICY "Enable read access for all" ON "public"."energy_readings"
FOR SELECT
TO public
USING (true);

-- 3. Create a policy for INSERT access
-- Ideally, this should be restricted to the "service_role" only, to prevent public manipulation.
-- IF your python script uses the Service Role Key (SUPABASE_SERVICE_ROLE_KEY), you can remove "public" and "anon" from the TO clause below.
-- However, since your current setup likely uses the Anon Key for ingestion, we must allow it for now.
-- WARNING: This allows anyone with your public anon key to insert data. 
-- Recommendation: Update your python script to use the Service Role Key and then allow only "service_role" here.

CREATE POLICY "Enable insert access for all" ON "public"."energy_readings"
FOR INSERT
TO public
WITH CHECK (true);

-- 4. Create a policy for UPDATE/DELETE access (Restricted)
-- We strictly restrict UPDATE/DELETE to service_role only (or no one, if not needed).
-- This prevents random users from deleting your history.

CREATE POLICY "Enable delete for service role only" ON "public"."energy_readings"
FOR DELETE
TO service_role
USING (true);

CREATE POLICY "Enable update for service role only" ON "public"."energy_readings"
FOR UPDATE
TO service_role
USING (true)
WITH CHECK (true);
