import { useState, useEffect, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  RefreshCw,
  Loader2,
  Wallet,
  Clock,
  BarChart3,
  Star,
  TrendingUp,
  TrendingDown,
} from "lucide-react";
import { getApiUrl } from "@/config/api";

interface Epoch {
  epoch_number: number;
  label: string;
  position_count: number;
  account_count: number;
}

interface TradingPair {
  market: string;
  volume: number;
  percentage: number;
}

interface AccountStats {
  account_index: number;
  account_name: string;
  total_volume: number;
  total_fees: number;
  positions: number;
  realised_pnl: number;
  points_earned: number;
  points_per_1m: number;
  avg_position_time: string;
  maker_volume: number;
  taker_volume: number;
  maker_pct: number;
  taker_pct: number;
  taker_fee_rate_bps: number;
  trading_pairs: TradingPair[];
}

interface CombinedStats {
  total_volume: number;
  total_fees: number;
  cost_per_point: number;
  total_positions: number;
  total_accounts: number;
  total_markets: number;
  total_pnl: number;
  total_points: number;
}

interface EpochData {
  epoch_number: number;
  epoch_label: string;
  combined_stats: CombinedStats;
  accounts: AccountStats[];
}

export const TradeHistoryWeekly = () => {
  const [epochs, setEpochs] = useState<Epoch[]>([]);
  const [selectedEpoch, setSelectedEpoch] = useState<string>("");
  const [epochData, setEpochData] = useState<EpochData | null>(null);
  const [loadingEpochs, setLoadingEpochs] = useState(true);
  const [loadingData, setLoadingData] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchEpochs = useCallback(async () => {
    setLoadingEpochs(true);
    setError(null);
    try {
      const res = await fetch(getApiUrl("/api/trade-history/epochs"));
      if (!res.ok) throw new Error(`Failed to fetch epochs: ${res.status}`);
      const data = await res.json();
      const epochList: Epoch[] = data.epochs || [];
      setEpochs(epochList);
      if (epochList.length > 0 && !selectedEpoch) {
        setSelectedEpoch(String(epochList[0].epoch_number));
      }
    } catch (err: any) {
      setError(err.message || "Failed to load epochs");
    } finally {
      setLoadingEpochs(false);
    }
  }, []);

  const fetchEpochData = useCallback(async (epochNumber: string) => {
    if (!epochNumber) return;
    setLoadingData(true);
    setError(null);
    try {
      const res = await fetch(
        getApiUrl(`/api/trade-history/epoch/${epochNumber}`)
      );
      if (!res.ok) throw new Error(`Failed to fetch epoch data: ${res.status}`);
      const data: EpochData = await res.json();
      setEpochData(data);
    } catch (err: any) {
      setError(err.message || "Failed to load epoch data");
    } finally {
      setLoadingData(false);
    }
  }, []);

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const res = await fetch(getApiUrl("/api/trade-history/refresh"), {
        method: "POST",
      });
      if (!res.ok) throw new Error(`Refresh failed: ${res.status}`);
      await fetchEpochs();
      if (selectedEpoch) {
        await fetchEpochData(selectedEpoch);
      }
    } catch (err: any) {
      setError(err.message || "Refresh failed");
    } finally {
      setRefreshing(false);
    }
  }, [fetchEpochs, fetchEpochData, selectedEpoch]);

  useEffect(() => {
    fetchEpochs();
  }, [fetchEpochs]);

  useEffect(() => {
    if (selectedEpoch) {
      fetchEpochData(selectedEpoch);
    }
  }, [selectedEpoch, fetchEpochData]);

  const stats = epochData?.combined_stats;

  return (
    <Card className="border-primary/20">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <CardTitle className="text-sm font-bold text-primary flex items-center gap-2">
            <BarChart3 className="w-4 h-4" />
            Weekly Trade History (Epochs)
          </CardTitle>

          <div className="flex items-center gap-2">
            {loadingEpochs ? (
              <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
            ) : (
              <Select value={selectedEpoch} onValueChange={setSelectedEpoch}>
                <SelectTrigger className="w-[320px] h-8 text-xs bg-muted/40 border-border/50">
                  <SelectValue placeholder="Select Epoch..." />
                </SelectTrigger>
                <SelectContent>
                  {epochs.map((ep) => (
                    <SelectItem
                      key={ep.epoch_number}
                      value={String(ep.epoch_number)}
                    >
                      {ep.label} ({ep.position_count} pos, {ep.account_count}{" "}
                      acc)
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}

            <Button
              variant="outline"
              size="sm"
              onClick={handleRefresh}
              disabled={refreshing}
              className="h-8 gap-1 text-xs"
            >
              <RefreshCw
                className={`w-3 h-3 ${refreshing ? "animate-spin" : ""}`}
              />
              Refresh Data
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {error && (
          <div className="text-sm text-destructive bg-destructive/10 border border-destructive/30 rounded-md p-3">
            {error}
          </div>
        )}

        {loadingData ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="w-6 h-6 animate-spin text-primary" />
            <span className="ml-2 text-sm text-muted-foreground">
              Loading epoch data...
            </span>
          </div>
        ) : stats ? (
          <>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <div className="bg-muted/40 rounded-lg p-4 border border-border/50">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                  Total Volume
                </div>
                <div className="text-2xl font-bold font-mono text-[#4ade80]">
                  {stats.total_volume.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </div>
                <div className="text-[10px] text-muted-foreground mt-1">
                  USD
                </div>
              </div>

              <div className="bg-muted/40 rounded-lg p-4 border border-border/50">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                  Total Fees Paid
                </div>
                <div className="text-2xl font-bold font-mono text-[#a78bfa]">
                  {stats.total_fees.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 6,
                  })}
                </div>
                <div className="text-[10px] text-muted-foreground mt-1">
                  USDC
                </div>
              </div>

              <div className="bg-muted/40 rounded-lg p-4 border border-border/50">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                  Cost Per Point
                </div>
                <div className="text-2xl font-bold font-mono text-[#22d3ee]">
                  {stats.cost_per_point.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 6,
                  })}
                </div>
                <div className="text-[10px] text-muted-foreground mt-1">
                  USDC
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="bg-muted/40 rounded-lg p-3 border border-border/50">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                  Positions
                </div>
                <div className="text-lg font-bold font-mono">
                  {stats.total_positions}
                </div>
              </div>
              <div className="bg-muted/40 rounded-lg p-3 border border-border/50">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                  Accounts
                </div>
                <div className="text-lg font-bold font-mono">
                  {stats.total_accounts}
                </div>
              </div>
              <div className="bg-muted/40 rounded-lg p-3 border border-border/50">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                  Total PnL
                </div>
                <div
                  className={`text-lg font-bold font-mono flex items-center gap-1 ${stats.total_pnl >= 0 ? "text-success" : "text-danger"}`}
                >
                  {stats.total_pnl >= 0 ? (
                    <TrendingUp className="w-4 h-4" />
                  ) : (
                    <TrendingDown className="w-4 h-4" />
                  )}
                  {stats.total_pnl >= 0 ? "+" : ""}
                  {stats.total_pnl.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 3,
                  })}
                </div>
              </div>
              <div className="bg-muted/40 rounded-lg p-3 border border-border/50">
                <div className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                  <Star className="w-3 h-3 text-yellow-500" />
                  Total Points
                </div>
                <div className="text-lg font-bold font-mono text-yellow-500">
                  {stats.total_points.toLocaleString(undefined, {
                    maximumFractionDigits: 1,
                  })}
                </div>
              </div>
            </div>

            {epochData && epochData.accounts.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-sm font-semibold text-muted-foreground uppercase tracking-wider">
                  Per-Account Details ({epochData.accounts.length} accounts)
                </h3>
                <Accordion type="single" collapsible className="w-full">
                  {epochData.accounts.map((acc) => (
                    <AccordionItem
                      key={acc.account_index}
                      value={`acc-${acc.account_index}`}
                      className="border-border/50"
                    >
                      <AccordionTrigger className="text-sm py-3 hover:no-underline">
                        <div className="flex items-center gap-3 w-full pr-4">
                          <Wallet className="w-4 h-4 text-primary flex-shrink-0" />
                          <span className="font-semibold truncate">
                            {acc.account_name}
                          </span>
                          <div className="flex items-center gap-3 ml-auto text-xs">
                            <span className="font-mono text-[#4ade80]">
                              $
                              {acc.total_volume.toLocaleString(undefined, {
                                maximumFractionDigits: 0,
                              })}
                            </span>
                            <span className="font-mono text-[#a78bfa]">
                              Fee:{" "}
                              {acc.total_fees.toLocaleString(undefined, {
                                maximumFractionDigits: 4,
                              })}
                            </span>
                            <Badge
                              variant="outline"
                              className="text-[10px] px-1.5"
                            >
                              {acc.positions} pos
                            </Badge>
                          </div>
                        </div>
                      </AccordionTrigger>
                      <AccordionContent>
                        <div className="space-y-4 px-2 pt-2">
                          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                            <div>
                              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                                Total Volume
                              </div>
                              <div className="text-sm font-bold font-mono text-[#4ade80]">
                                $
                                {acc.total_volume.toLocaleString(undefined, {
                                  maximumFractionDigits: 2,
                                })}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                                Total Fees
                              </div>
                              <div className="text-sm font-bold font-mono text-[#a78bfa]">
                                {acc.total_fees.toLocaleString(undefined, {
                                  maximumFractionDigits: 4,
                                })}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                                <Clock className="w-3 h-3" />
                                Avg Position Time
                              </div>
                              <div className="text-sm font-bold font-mono">
                                {acc.avg_position_time}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                                Positions
                              </div>
                              <div className="text-sm font-bold font-mono">
                                {acc.positions}
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                                <Star className="w-3 h-3 text-yellow-500" />
                                Points Earned
                              </div>
                              <div className="text-sm font-bold font-mono text-yellow-500">
                                {acc.points_earned.toLocaleString(undefined, {
                                  maximumFractionDigits: 1,
                                })}{" "}
                                pts
                              </div>
                            </div>
                            <div>
                              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                                Points / 1M
                              </div>
                              <div className="text-sm font-bold font-mono text-yellow-400">
                                {acc.points_per_1m.toLocaleString(undefined, {
                                  maximumFractionDigits: 1,
                                })}{" "}
                                pts
                              </div>
                            </div>
                          </div>

                          <div>
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider mb-1">
                              Realised PnL
                            </div>
                            <div
                              className={`text-sm font-bold font-mono flex items-center gap-1 ${acc.realised_pnl >= 0 ? "text-success" : "text-danger"}`}
                            >
                              {acc.realised_pnl >= 0 ? (
                                <TrendingUp className="w-3 h-3" />
                              ) : (
                                <TrendingDown className="w-3 h-3" />
                              )}
                              {acc.realised_pnl >= 0 ? "+" : ""}
                              {acc.realised_pnl.toLocaleString(undefined, {
                                minimumFractionDigits: 3,
                                maximumFractionDigits: 3,
                              })}
                            </div>
                          </div>

                          <div className="space-y-2">
                            <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                              Maker / Taker Breakdown
                            </div>
                            <div className="flex items-center gap-2">
                              <div className="flex-1">
                                <div className="flex justify-between text-[10px] mb-1">
                                  <span className="text-[#22d3ee]">
                                    Maker {acc.maker_pct.toFixed(1)}%
                                  </span>
                                  <span className="text-[#f97316]">
                                    Taker {acc.taker_pct.toFixed(1)}%
                                  </span>
                                </div>
                                <div className="h-2 rounded-full bg-muted overflow-hidden flex">
                                  <div
                                    className="h-full bg-[#22d3ee] transition-all"
                                    style={{ width: `${acc.maker_pct}%` }}
                                  />
                                  <div
                                    className="h-full bg-[#f97316] transition-all"
                                    style={{ width: `${acc.taker_pct}%` }}
                                  />
                                </div>
                              </div>
                            </div>
                            <div className="grid grid-cols-3 gap-2 text-xs">
                              <div>
                                <span className="text-muted-foreground">
                                  Maker Vol:{" "}
                                </span>
                                <span className="font-mono text-[#22d3ee]">
                                  $
                                  {acc.maker_volume.toLocaleString(undefined, {
                                    maximumFractionDigits: 2,
                                  })}
                                </span>
                              </div>
                              <div>
                                <span className="text-muted-foreground">
                                  Taker Vol:{" "}
                                </span>
                                <span className="font-mono text-[#f97316]">
                                  $
                                  {acc.taker_volume.toLocaleString(undefined, {
                                    maximumFractionDigits: 2,
                                  })}
                                </span>
                              </div>
                              <div>
                                <span className="text-muted-foreground">
                                  Taker Fee Rate:{" "}
                                </span>
                                <span className="font-mono">
                                  {acc.taker_fee_rate_bps.toFixed(2)} bps
                                </span>
                              </div>
                            </div>
                          </div>

                          {acc.trading_pairs.length > 0 && (
                            <div className="space-y-2">
                              <div className="text-[10px] text-muted-foreground uppercase tracking-wider">
                                Trading Pairs
                              </div>
                              <div className="flex flex-wrap gap-2">
                                {acc.trading_pairs.map((pair) => (
                                  <div
                                    key={pair.market}
                                    className="flex items-center gap-2 bg-muted/40 rounded-md px-3 py-1.5 border border-border/50"
                                  >
                                    <span className="text-xs font-semibold">
                                      {pair.market}
                                    </span>
                                    <Badge
                                      variant="outline"
                                      className="text-[10px] px-1.5 border-primary/50 text-primary"
                                    >
                                      {pair.percentage.toFixed(1)}%
                                    </Badge>
                                    <span className="text-[10px] font-mono text-muted-foreground">
                                      $
                                      {pair.volume.toLocaleString(undefined, {
                                        maximumFractionDigits: 0,
                                      })}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </AccordionContent>
                    </AccordionItem>
                  ))}
                </Accordion>
              </div>
            )}
          </>
        ) : (
          !loadingEpochs && (
            <div className="text-center py-8 text-muted-foreground text-sm">
              Select an epoch to view trade history statistics
            </div>
          )
        )}
      </CardContent>
    </Card>
  );
};
