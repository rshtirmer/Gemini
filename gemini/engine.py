import plotly.graph_objects as go
import pandas as pd
import numpy as np
import warnings
import time

# Local imorts
from . import exchange, helpers

class backtest():
    """An object representing a backtesting simulation."""
    def __init__(self, data):
        """Initate the backtest.

        :param data: An HLOCV+ pandas dataframe with a datetime index
        :type data: pandas.DataFrame

        :return: A bactesting simulation
        :rtype: backtest
        """  
        if not isinstance(data, pd.DataFrame):
            raise ValueError("Data must be a pandas dataframe")

        missing = set(['high', 'low', 'open', 'close', 'volume'])-set(data.columns)
        if len(missing) > 0:
            msg = "Missing {0} column(s), dataframe must be HLOCV+".format(list(missing))
            warnings.warn(msg)

        self.data = data

    def start(self, initial_capital, logic):
        """Start backtest.

        :param initial_capital: Starting capital to fund account
        :type initial_capital: float
        :param logic: A function that will be applied to each lookback period of the data
        :type logic: function

        :return: A bactesting simulation
        :rtype: backtest
        """         
        self.tracker = []
        self.account = exchange.account(initial_capital)

        # Enter backtest ---------------------------------------------  
        for index, today in self.data.iterrows():
    
            date = today['date']
            equity = self.account.total_value(today['close'])

            # Stop loss & Take Profit handling
            for p in self.account.positions:
                if p.type == "long":
                    if p.stop_hit(today['low']):
                        self.account.close_position(p, 1.0, today['low'])
                    elif p.tp_hit(today['high']):
                        self.account.close_position(p, 1.0, p.exit_price)
                    else:
                        if p.trailing_stop:
                            if today['close'] > today['open']:
                                p.stop_adjust(today['close'])

                if p.type == "short":
                    if p.stop_hit(today['high']):
                        self.account.close_position(p, 1.0, today['high'])
                    elif p.tp_hit(today['low']):
                        self.account.close_position(p, 1.0, p.exit_price)
                    else:
                        if p.trailing_stop:
                            if today['close'] < today['open']:
                                p.stop_adjust(today['close'])

            self.account.purge_positions()

            # TODO: Take profit handling

            # Update account variables
            self.account.date = date
            self.account.equity.append(equity)

            # Equity tracking
            self.tracker.append({'date': date, 
                                 'benchmark_equity' : today['close'],
                                 'strategy_equity' : equity})

            # Execute trading logic
            lookback = self.data[0:index+1]
            logic(self.account, lookback)

            # Cleanup empty positions
            self.account.purge_positions()     
        # ------------------------------------------------------------

        # For pyfolio
        df = pd.DataFrame(self.tracker)
        df['benchmark_return'] = (df.benchmark_equity-df.benchmark_equity.shift(1))/df.benchmark_equity.shift(1)
        df['strategy_return'] = (df.strategy_equity-df.strategy_equity.shift(1))/df.strategy_equity.shift(1)
        df.index = df['date']
        del df['date']
        return df

    def results(self):   
        """Print results"""           
        print("-------------- Results ----------------\n")
        being_price = self.data.iloc[0]['open']
        final_price = self.data.iloc[-1]['close']

        pc = helpers.percent_change(being_price, final_price)
        print("Buy and Hold : {0}%".format(round(pc*100, 2)))
        print("Net Profit   : {0}".format(round(helpers.profit(self.account.initial_capital, pc), 2)))
        
        pc = helpers.percent_change(self.account.initial_capital, self.account.total_value(final_price))
        print("Strategy     : {0}%".format(round(pc*100, 2)))
        print("Net Profit   : {0}".format(round(helpers.profit(self.account.initial_capital, pc), 2)))

        longs  = len([t for t in self.account.opened_trades if t.type == 'long'])
        sells  = len([t for t in self.account.closed_trades if t.type == 'long'])
        shorts = len([t for t in self.account.opened_trades if t.type == 'short'])
        covers = len([t for t in self.account.closed_trades if t.type == 'short'])

        print("Longs        : {0}".format(longs))
        print("sells        : {0}".format(sells))
        print("shorts       : {0}".format(shorts))
        print("covers       : {0}".format(covers))
        print("--------------------")
        print("Total Trades : {0}".format(longs + sells + shorts + covers))
        print("\n---------------------------------------")
    
    def chart(self, show_trades=True, title="Equity Curve"):
        """Chart results.

        :param show_trades: Show trades on plot
        :type show_trades: bool
        :param title: Plot title
        :type title: str
        """
        fig = go.Figure()
        
        shares = self.account.initial_capital/self.data.iloc[0]['open']
        base_equity = [price*shares for price in self.data['open']]      

        fig.add_trace(go.Scatter(
                        x=self.data['date'],
                        y=base_equity,
                        name="Buy and Hold"))

        fig.add_trace(go.Scatter(
                        x=self.data['date'],
                        y=self.account.equity,
                        name="Strategy"))
        x_long  = []
        y_long  = []
        x_short = []
        y_short = []
        x_sell  = []
        y_sell  = []
        x_cover = []
        y_cover = []
        
        if show_trades:
            for trade in self.account.opened_trades:
                try:
                    x = time.mktime(trade.date.timetuple())*1000
                    y = self.account.equity[np.where(self.data['date'] == trade.date.strftime("%Y-%m-%d"))[0][0]]
                    if trade.type == 'long': 
                        x_long.append(x)
                        y_long.append(y)
                    elif trade.type == 'short':
                        x_short.append(x)
                        y_short.append(y)
                except Exception as E:
                    print(E)

            for trade in self.account.closed_trades:
                try:
                    x = time.mktime(trade.date.timetuple())*1000
                    y = self.account.equity[np.where(self.data['date'] == trade.date.strftime("%Y-%m-%d"))[0][0]]
                    if trade.type == 'long': 
                        x_sell.append(x)
                        y_sell.append(y)
                    elif trade.type == 'short':
                        x_cover.append(x)
                        y_cover.append(y)
                except Exception as E:
                    print(E)
        
        fig.add_trace(go.Scatter(x=x_long, y=y_long, name='long', mode='markers', marker_color='green', marker_size=8))
        fig.add_trace(go.Scatter(x=x_short, y=y_short, name='short', mode='markers', marker_color='red', marker_size=8))
        fig.add_trace(go.Scatter(x=x_sell, y=y_sell, name='sell', mode='markers', marker_color='blue', marker_size=8))
        fig.add_trace(go.Scatter(x=x_cover, y=y_cover, name='cover', mode='markers', marker_color='orange', marker_size=8))
        
        fig.update_layout(
            title=title,
        )
   
        fig.write_html('chart.html', auto_open=True)
