CREATE EXTENSION IF NOT EXISTS "pg_graphql";
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "plpgsql";
CREATE EXTENSION IF NOT EXISTS "supabase_vault";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
--
-- PostgreSQL database dump
--


-- Dumped from database version 17.6
-- Dumped by pg_dump version 17.7

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--



--
-- Name: get_latest_market_data(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.get_latest_market_data() RETURNS jsonb
    LANGUAGE plpgsql SECURITY DEFINER
    SET search_path TO 'public'
    AS $$
DECLARE
  result JSONB;
BEGIN
  SELECT jsonb_build_object(
    'positions', positions,
    'balance', balance,
    'extended_data', extended_data,
    'public_prices', public_prices,
    'updated_at', updated_at
  )
  INTO result
  FROM public.market_data_snapshots
  ORDER BY updated_at DESC
  LIMIT 1;
  
  RETURN COALESCE(result, '{}'::jsonb);
END;
$$;


SET default_table_access_method = heap;

--
-- Name: market_data_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.market_data_snapshots (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    positions jsonb DEFAULT '[]'::jsonb NOT NULL,
    balance jsonb,
    extended_data jsonb,
    public_prices jsonb DEFAULT '{}'::jsonb,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL,
    trades json DEFAULT '[]'::json
);


--
-- Name: market_data_snapshots market_data_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.market_data_snapshots
    ADD CONSTRAINT market_data_snapshots_pkey PRIMARY KEY (id);


--
-- Name: idx_market_data_snapshots_updated_at; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_market_data_snapshots_updated_at ON public.market_data_snapshots USING btree (updated_at DESC);


--
-- Name: market_data_snapshots Anyone can read market data snapshots; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Anyone can read market data snapshots" ON public.market_data_snapshots FOR SELECT USING (true);


--
-- Name: market_data_snapshots Service role can insert market data snapshots; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role can insert market data snapshots" ON public.market_data_snapshots FOR INSERT WITH CHECK (true);


--
-- Name: market_data_snapshots Service role can update market data snapshots; Type: POLICY; Schema: public; Owner: -
--

CREATE POLICY "Service role can update market data snapshots" ON public.market_data_snapshots FOR UPDATE USING (true);


--
-- Name: market_data_snapshots; Type: ROW SECURITY; Schema: public; Owner: -
--

ALTER TABLE public.market_data_snapshots ENABLE ROW LEVEL SECURITY;

--
-- PostgreSQL database dump complete
--


