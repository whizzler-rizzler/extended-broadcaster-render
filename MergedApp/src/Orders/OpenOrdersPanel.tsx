import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Clock, FileText, ChevronDown, ChevronUp } from "lucide-react";
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
  accountName: string;
  market: string;
  side: string;
  orderType: string;
  price: string;
  qty: string;
  filledQty: string;
  status: string;
  createdTime: number;
}

interface OpenOrdersPanelProps {
  accounts: Map<string, SingleAccountData>;
  lastUpdate: Date;
}

export const OpenOrdersPanel = ({ accounts, lastUpdate }: OpenOrdersPanelProps) => {
  const [isExpanded, setIsExpanded] = useState(true);

  // Aggregate orders from all accounts - updates automatically with WebSocket data
  const orders = useMemo(() => {
    const allOrders: Order[] = [];
    
    accounts.forEach((account, accountId) => {
      // Extract account display name
      const accountNameMatch = accountId.match(/Extended_(\d+)/);
      const accountName = accountNameMatch ? `Extended ${accountNameMatch[1]}` : account.name || accountId;
      
      // Process orders from this account
      const accountOrders = account.orders || [];
      accountOrders.forEach((o: any) => {
        allOrders.push({
          id: o.id || o.orderId || `${accountId}_${o.market}_${o.createdTime}`,
          accountName,
          market: o.market || o.symbol || 'UNKNOWN',
          side: o.side || 'UNKNOWN',
          orderType: o.orderType || o.type || 'LIMIT',
          price: String(o.price || '0'),
          qty: String(o.qty || o.size || o.quantity || '0'),
          filledQty: String(o.filledQty || o.filled || '0'),
          status: o.status || 'ACTIVE',
          createdTime: o.createdTime || o.timestamp || Date.now(),
        });
      });
    });
    
    // Sort by time descending
    allOrders.sort((a, b) => b.createdTime - a.createdTime);
    
    return allOrders;
  }, [accounts]);

  const formatTime = (timestamp: number) => {
    return new Date(timestamp).toLocaleString('pl-PL', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const formatPrice = (price: string) => {
    const num = parseFloat(price);
    if (isNaN(num)) return '0.00';
    return num.toLocaleString('pl-PL', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 4,
    });
  };

  return (
    <Card className="border-primary/20">
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            Otwarte Zlecenia (wszystkie konta)
          </CardTitle>
          <div className="flex items-center gap-3">
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
          <div className="space-y-4">
            <div className="text-sm text-muted-foreground">
              Wszystkie zlecenia ({orders.length})
            </div>
            <div className="rounded-md border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Konto</TableHead>
                    <TableHead>Rynek</TableHead>
                    <TableHead>Strona</TableHead>
                    <TableHead>Typ</TableHead>
                    <TableHead className="text-right">Cena</TableHead>
                    <TableHead className="text-right">Ilość</TableHead>
                    <TableHead className="text-right">Wypełnione</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Czas</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {orders.map((order) => (
                    <TableRow key={order.id}>
                      <TableCell className="font-medium text-primary">
                        {order.accountName}
                      </TableCell>
                      <TableCell className="font-medium">{order.market}</TableCell>
                      <TableCell>
                        <Badge variant={order.side === 'BUY' ? 'default' : 'destructive'}>
                          {order.side}
                        </Badge>
                      </TableCell>
                      <TableCell>{order.orderType}</TableCell>
                      <TableCell className="text-right font-mono">
                        {formatPrice(order.price)}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {order.qty}
                      </TableCell>
                      <TableCell className="text-right font-mono">
                        {order.filledQty || '0'}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{order.status}</Badge>
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">
                        {formatTime(order.createdTime)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}
      </CardContent>}
    </Card>
  );
};
