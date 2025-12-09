import { corsHeaders } from '../_shared/cors.ts';
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2.39.3';

interface MarketDataResponse {
  success: boolean;
  data?: {
    positions: any[];
    balance: any;
    extended_data: any;
    public_prices: any;
    trades: any[];
    updated_at: string;
  };
  error?: string;
}

Deno.serve(async (req) => {
  // Handle CORS preflight requests
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: corsHeaders });
  }

  try {
    console.log('📊 [API] Fetching market data from database...');

    // Initialize Supabase client
    const supabaseUrl = Deno.env.get('SUPABASE_URL')!;
    const supabaseKey = Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!;
    const supabase = createClient(supabaseUrl, supabaseKey);

    // Get latest snapshot from database
    const { data: snapshot, error } = await supabase
      .from('market_data_snapshots')
      .select('*')
      .order('updated_at', { ascending: false })
      .limit(1)
      .maybeSingle();

    if (error) {
      throw new Error(`Database error: ${error.message}`);
    }

    if (!snapshot) {
      return new Response(
        JSON.stringify({
          success: false,
          error: 'No market data available yet',
        } as MarketDataResponse),
        {
          headers: {
            ...corsHeaders,
            'Content-Type': 'application/json',
          },
          status: 404,
        }
      );
    }

    console.log('✅ [API] Successfully fetched market data from database');

    // Format response
    const marketData: MarketDataResponse = {
      success: true,
      data: {
        positions: snapshot.positions || [],
        balance: snapshot.balance || null,
        extended_data: snapshot.extended_data || null,
        public_prices: snapshot.public_prices || {},
        trades: snapshot.trades || [],
        updated_at: snapshot.updated_at,
      },
    };

    return new Response(
      JSON.stringify(marketData),
      {
        headers: {
          ...corsHeaders,
          'Content-Type': 'application/json',
        },
        status: 200,
      }
    );

  } catch (error) {
    console.error('❌ [API] Error fetching market data:', error);
    
    const errorResponse: MarketDataResponse = {
      success: false,
      error: error instanceof Error ? error.message : 'Unknown error occurred',
    };

    return new Response(
      JSON.stringify(errorResponse),
      {
        headers: {
          ...corsHeaders,
          'Content-Type': 'application/json',
        },
        status: 500,
      }
    );
  }
});
