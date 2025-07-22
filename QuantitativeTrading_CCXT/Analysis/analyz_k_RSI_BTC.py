import ccxt
from datetime import datetime

# 模拟账户
account_money = 60000
account_coin = 0
charge_fee = 0
max_x = 0
max_time = 0

symbol = 'BTCUSDT'  # 要交易的币种************
tra_amounts = 0.001  # 底仓数量*************
float_price = 1500  # 策略的加仓或平仓价格**********
min_amount = 0.001  # 此币最小下单数量************

category = 'linear'  # 合约
tra_side = 'Buy'  # 单向持仓策略，BUY为买，SELL为卖
tra_type = 'Market'  # 策略交易类型LIMIT/MARKET

all_amounts = 0  # 持仓数
loss_x = 0  # 亏损仓位
open_position_price = 0
charges = 0

high_point = 0
float_width = 3000
low_point = high_point - float_width
take_profit = 1500
stop_lose = 800
back_board = 100  # 高点实时更新，不好为0或负数

high_buy = high_point + float_price / 1.5
high_sell = high_point - float_price
low_buy = low_point + float_price
low_sell = low_point - float_price / 1.5

have_position = 0
position_status = ''
high_sell_status = 0
low_buy_status = 0
high_sell_commit = 0
low_buy_commit = 0

RSI12_queue = [2, -1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0]
RSI27_queue = [2, -1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
RSI45_queue = [2, -1, -1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
               0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
prices_queue = []

RSI12_point = -1
RSI27_point = -1
RSI45_point = -1


def create_order(exchange_p, param):
    global account_money, account_coin, charge_fee
    if param['side'] == 'Buy':
        account_money = account_money - float(param['qty']) * exchange_p
        account_coin = account_coin + float(param['qty'])
        charge_fee = charge_fee + float(param['qty']) * exchange_p * 0.0005
    elif param['side'] == 'Sell':
        account_money = account_money + float(param['qty']) * exchange_p
        account_coin = account_coin - float(param['qty'])
        charge_fee = charge_fee + float(param['qty']) * exchange_p * 0.0005


def clear_position(amount, side, time):
    global max_x, max_time
    order_params = {
        'category': category,
        'symbol': symbol,
        'side': side,
        'orderType': tra_type,
        'qty': str(amount),
    }
    create_order(price, order_params)
    if amount > max_x:
        max_x = amount
        max_time = time

    print('清仓', amount, '价格', price, '时间', time)


def getonedayklinedata_1_min(bybit, start):
    kline = []
    param = {
        'category': category,
        'symbol': symbol,
        'interval': '1',  # 时间颗粒度1分钟
        'limit': '1000',  # 每页数量限制
        'end': (start + 24 * 60 * 60) * 1000 - 1,
        'start': start * 1000,
    }
    kline_raw1 = bybit.public_get_v5_market_kline(params=param)
    kline = kline + kline_raw1['result']['list']
    param = {
        'category': category,
        'symbol': symbol,
        'interval': '1',  # 时间颗粒度3分钟
        'limit': '1000',  # 每页数量限制
        'end': (start + 440 * 60) * 1000,
        'start': start * 1000,
    }
    kline_raw2 = bybit.public_get_v5_market_kline(params=param)
    kline = kline + kline_raw2['result']['list']
    return kline


def getonedayklinedata_15_min(bybit, start):
    param = {
        'category': category,
        'symbol': symbol,
        'interval': '15',  # 时间颗粒度15分钟
        'limit': '1000',  # 每页数量限制
        'end': (start + 24 * 60 * 60) * 1000 - 1,
        'start': start * 1000,
    }
    kline = bybit.public_get_v5_market_kline(params=param)
    return kline['result']['list']


def calculate_RSI(prices, period=12):
    deltas = prices
    # 初始化前period天的平均上涨和下跌
    avg_gain = sum(max(d, 0) for d in deltas[:period]) / period
    avg_loss = abs(sum(min(d, 0) for d in deltas[:period])) / period

    # 计算后续的平滑平均
    for d in deltas[period:]:
        gain = max(d, 0)
        loss = abs(min(d, 0))
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    # 处理没有下跌的情况
    if avg_loss == 0:
        return 100.0

    # 计算RS和RSI
    RS = avg_gain / avg_loss
    RSI = 100 - (100 / (1 + RS))

    return round(RSI, 3)


def update_rsi12_queue(price):
    global RSI12_point, RSI12_queue
    RSI12_point = (RSI12_point + 1) % 12
    RSI12_queue[RSI12_point] = price


def update_rsi27_queue(price):
    global RSI27_point, RSI27_queue
    RSI27_point = (RSI27_point + 1) % 27
    RSI27_queue[RSI27_point] = price


def update_rsi45_queue(price):
    global RSI45_point, RSI45_queue
    RSI45_point = (RSI45_point + 1) % 45
    RSI45_queue[RSI45_point] = price


oneday = 24 * 60 * 60
time202561 = 1748707200 + oneday * -367
end_time = 1748707200 + oneday * 0

bybit = ccxt.bybit({
    'timeout': 10000,
    'enableRateLimit': True
})

now_time = bybit.iso8601(bybit.milliseconds())
print('交易所当前时间:', now_time, '   毫秒为', bybit.milliseconds())

# 加载市场数据
bybit_markets = bybit.load_markets()

i = 200
while time202561 < end_time:

    kline = getonedayklinedata_15_min(bybit, time202561)

    for kdata in reversed(kline):
        openPrice = float(kdata[1])  # 开盘价
        closePrice = float(kdata[4])  # 收盘价
        highPrice = float(kdata[2])  # 最高价
        lowPrice = float(kdata[3])  # 最低价
        volume = float(kdata[5])  # 交易量
        turnover = float(kdata[6])  # 交易额
        ktime = datetime.fromtimestamp(int(kdata[0]) / 1000)
        # print('k线时间:', datetime.fromtimestamp(int(kdata[0])/1000), '开盘价', openPrice, '收盘价', closePrice, '最高价', highPrice, '最低价', lowPrice, '交易量', volume, '交易额', turnover)

        # update_rsi12_queue(closePrice - openPrice)
        # update_rsi27_queue(closePrice - openPrice)
        # update_rsi45_queue(closePrice - openPrice)
        prices_queue.append(closePrice - openPrice)
        if i > 0:
            i = i - 1
            continue

        RSI12 = calculate_RSI(prices_queue[len(prices_queue) - 195:], 12)
        RSI27 = calculate_RSI(prices_queue[len(prices_queue) - 195:], 27)
        RSI45 = calculate_RSI(prices_queue[len(prices_queue) - 195:], 45)

        # print('k线时间', datetime.fromtimestamp(int(kdata[0])/1000), '  RSI12', RSI12, '  RSI27', RSI27, '  RSI45', RSI45)
        # print(prices_queue)
        price = closePrice

        # 开空
        if RSI12 - RSI27 > 13:
            if tra_side == 'Buy' and all_amounts > 0:
                tra_side = 'Sell'
                clear_position(all_amounts, tra_side, ktime)
                all_amounts = 0
            qty = 0.05
            order_params = {
                'category': category,
                'symbol': symbol,
                'side': 'Sell',
                'orderType': tra_type,
                'qty': str(qty),
            }
            create_order(price, order_params)
            all_amounts = all_amounts + qty
            print('开空', qty, '总仓位', all_amounts, '价格', price, '时间', ktime)
        elif RSI12 - RSI27 > 12:
            if tra_side == 'Buy' and all_amounts > 0:
                tra_side = 'Sell'
                clear_position(all_amounts, tra_side, ktime)
                all_amounts = 0
            qty = 0.01
            order_params = {
                'category': category,
                'symbol': symbol,
                'side': 'Sell',
                'orderType': tra_type,
                'qty': str(qty),
            }
            create_order(price, order_params)
            all_amounts = all_amounts + qty
            print('开空', qty, '总仓位', all_amounts, '价格', price, '时间', ktime)
        elif RSI12 - RSI27 > 11:
            if tra_side == 'Buy' and all_amounts > 0:
                tra_side = 'Sell'
                clear_position(all_amounts, tra_side, ktime)
                all_amounts = 0
            qty = 0.001
            order_params = {
                'category': category,
                'symbol': symbol,
                'side': 'Sell',
                'orderType': tra_type,
                'qty': str(qty),
            }
            create_order(price, order_params)
            all_amounts = all_amounts + qty
            print('开空', qty, '总仓位', all_amounts, '价格', price, '时间', ktime)

        # 开多
        if RSI12 - RSI27 < -13:
            if tra_side == 'Sell' and all_amounts > 0:
                tra_side = 'Buy'
                clear_position(all_amounts, tra_side, ktime)
                all_amounts = 0
            qty = 0.05
            order_params = {
                'category': category,
                'symbol': symbol,
                'side': 'Buy',
                'orderType': tra_type,
                'qty': str(qty),
            }
            create_order(price, order_params)
            all_amounts = all_amounts + qty
            print('开多', qty, '总仓位', all_amounts, '价格', price, '时间', ktime)
        elif RSI12 - RSI27 < -12:
            if tra_side == 'Sell' and all_amounts > 0:
                tra_side = 'Buy'
                clear_position(all_amounts, tra_side, ktime)
                all_amounts = 0
            qty = 0.01
            order_params = {
                'category': category,
                'symbol': symbol,
                'side': 'Buy',
                'orderType': tra_type,
                'qty': str(qty),
            }
            create_order(price, order_params)
            all_amounts = all_amounts + qty
            print('开多', qty, '总仓位', all_amounts, '价格', price, '时间', ktime)
        elif RSI12 - RSI27 < -11:
            if tra_side == 'Sell' and all_amounts > 0:
                tra_side = 'Buy'
                clear_position(all_amounts, tra_side, ktime)
                all_amounts = 0
            qty = 0.001
            order_params = {
                'category': category,
                'symbol': symbol,
                'side': 'Buy',
                'orderType': tra_type,
                'qty': str(qty),
            }
            create_order(price, order_params)
            all_amounts = all_amounts + qty
            print('开多', qty, '总仓位', all_amounts, '价格', price, '时间', ktime)

    time202561 = time202561 + oneday

print('账户最终余额', account_money)
print('结束时还有合约张数：', account_coin)
print('最大持仓张数', max_x, '时间', max_time)
print('共产生手续费', charge_fee)
