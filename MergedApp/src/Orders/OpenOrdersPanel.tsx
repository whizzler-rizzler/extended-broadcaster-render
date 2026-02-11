import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Clock, FileText, ChevronDown, ChevronUp, ArrowUpDown } from "lucide-react";
import { useState, useMemo } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { SingleAccountData } from "@/types/multiAccount";

interface Order {
  id: string;
  accountIndex: number;
  accountName: string;
  market: string;
  side: string;
  orderType: string;
  price: string;
  triggerPrice: string;
  qty: string;
  filledQty: string;
  status: string;
  createdTime: number;
}

type SortField = "account" | "market" | "time";
type SortDir = "asc" | "desc";

interface OpenOrdersPanelProps {
  accounts: Map<string, SingleAccountData>;
  lastUpdate: Date;
}

export const OpenOrdersPanel = ({ accounts, lastUpdate }: OpenOrdersPanelProps) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [sortField, setSortField] = useState<SortField>("account");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDir("asc");
    }
  };

  const orders = useMemo(() => {
    const allOrders: Order[] = [];
    
    accounts.forEach((account, accountId) => {
      const accountNameMatch = accountId.match(/Extended_(\d+)/);
      const accountIndex = accountNameMatch ? parseInt(accountNameMatch[1]) : 0;
      const accountName = accountNameMatch ? `Ext ${accountNameMatch[1]}` : account.name || accountId;
      
      const rawOrders = account.orders;
      let orderList: any[] = [];
      if (Array.isArray(rawOrders)) {
        orderList = rawOrders;
      } else if (rawOrders && typeof rawOrders === 'object') {
        const dataField = (rawOrders as any).data;
        if (Array.isArray(dataField)) {
          orderList = dataField;
        }
      }

      orderList.forEach((o: any) => {
        let price = '';
        let triggerPrice = '';
        const orderType = o.type || o.orderType || 'LIMIT';

        if (orderType === 'TPSL' || orderType === 'TP' || orderType === 'SL') {
          const tp = o.takeProfit;
          const sl = o.stopLoss;
          if (tp && tp.triggerPrice) {
            triggerPrice = `TP: ${tp.triggerPrice}`;
            price = tp.price || tp.triggerPrice;
          }
          if (sl && sl.triggerPrice) {
            triggerPrice += triggerPrice ? ` / SL: ${sl.triggerPrice}` : `SL: ${sl.triggerPrice}`;
            if (!price) price = sl.price || sl.triggerPrice;
          }
        } else {
          price = String(o.price || '0');
        }

        const qty = o.qty || o.size || o.quantity || '0';
        const tpSlType = o.tpSlType;

        allOrders.push({
          id: String(o.id || o.orderId || `${accountId}_${o.market}_${o.createdTime}`),
          accountIndex,
          accountName,
          market: o.market || o.symbol || 'UNKNOWN',
          side: o.side || 'UNKNOWN',
          orderType,
          price,
          triggerPrice,
          qty: tpSlType === 'POSITION' ? 'POS' : String(qty),
          filledQty: String(o.filledQty || o.filled || '0'),
          status: o.status || 'ACTIVE',
          createdTime: o.createdTime || o.timestamp || Date.now(),
        });
      });
    });
    
    allOrders.sort((a, b) => {
      let cmp = 0;
      switch (sortField) {
        case "account":
          cmp = a.accountIndex - b.accountIndex;
          break;
        case "market":
          cmp = a.market.localeCompare(b.market);
          break;
        case "time":
          cmp = a.createdTime - b.createdTime;
          break;
      }
      return sortDir === "asc" ? cmp : -cmp;
    });
    
    return allOrders;
  }, [accounts, sortField, sortDir]);

  const formatTime = (timestamp: number) => {
    return new Date(timestamp).toLocaleString('pl-PL', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const formatPrice = (price: string) => {
    const num = parseFloat(price);
    if (isNaN(num) || num === 0) return '-';
    return num.toLocaleString('pl-PL', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    });
  };

  const SortableHead = ({ field, children, className }: { field: SortField; children: React.ReactNode; className?: string }) => (
    <TableHead
      className={`cursor-pointer select-none hover:text-primary ${className || ''}`}
      onClick={() => toggleSort(field)}
    >
      <span className="flex items-center gap-1">
        {children}
        <ArrowUpDown className={`w-3 h-3 ${sortField === field ? 'text-primary' : 'text-muted-foreground/50'}`} />
      </span>
    </TableHead>
  );

  return (
    <Card className="border-primary/20">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            Otwarte Zlecenia (wszystkie konta)
          </CardTitle>
          <div className="flex items-center gap-3">
            <Badge variant="outline" className="text-xs">
              {orders.length} zleceń
            </Badge>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Clock className="h-4 w-4" />
              {lastUpdate.toLocaleTimeString('pl-PL')}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsExpanded(!isExpanded)}
              className="h-6 px-2"
            >
              {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </Button>
          </div>
        </div>
      </CardHeader>
      {isExpanded && <CardContent>
        {orders.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            Brak otwartych zleceń
          </div>
        ) : (
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableHead field="account">Konto</SortableHead>
                  <SortableHead field="market">Rynek</SortableHead>
                  <TableHead>Strona</TableHead>
                  <TableHead>Typ</TableHead>
                  <TableHead className="text-right">Cena / Trigger</TableHead>
                  <TableHead className="text-right">Ilość</TableHead>
                  <TableHead className="text-right">Wypełnione</TableHead>
                  <TableHead>Status</TableHead>
                  <SortableHead field="time">Czas</SortableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {orders.map((order) => (
                  <TableRow key={order.id}>
                    <TableCell className="font-medium text-primary whitespace-nowrap">
                      {order.accountName}
                    </TableCell>
                    <TableCell className="font-medium">{order.market}</TableCell>
                    <TableCell>
                      <Badge variant={order.side === 'BUY' ? 'default' : 'destructive'} className="text-[10px] px-1.5">
                        {order.side}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-xs">{order.orderType}</TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {order.triggerPrice ? (
                        <span className="text-yellow-400" title={order.triggerPrice}>
                          {order.triggerPrice}
                        </span>
                      ) : (
                        formatPrice(order.price)
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {order.qty === 'POS' ? (
                        <span className="text-muted-foreground">Pozycja</span>
                      ) : (
                        formatPrice(order.qty)
                      )}
                    </TableCell>
                    <TableCell className="text-right font-mono text-xs">
                      {formatPrice(order.filledQty)}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px] px-1.5">{order.status}</Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground whitespace-nowrap">
                      {formatTime(order.createdTime)}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>}
    </Card>
  );
};
