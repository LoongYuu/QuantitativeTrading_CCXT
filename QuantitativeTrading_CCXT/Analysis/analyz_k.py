import ccxt
from datetime import datetime


def getonedayklinedata(bybit, start):
    kline = []
    param = {
        'category': category,
        'symbol': symbol,
        'interval': '1',  # 时间颗粒度3分钟
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


# 交易类型
symbol = 'BTCUSDT'  # 要交易的币种************
tra_amounts = 10.0  # 底仓数量*************
float_price = 300  # 策略的加仓或平仓价格**********
price_PRECISION = 4  # 此币的价格精度,小数点后几位**********

category = 'linear'  # 合约
tra_side = 'Buy'  # 单向持仓策略，BUY为买，SELL为卖
tra_type = 'Market'  # 策略交易类型LIMIT/MARKET

oneday = 24 * 60 * 60
time202561 = 1748707200
time202562 = 1748793600

bybit = ccxt.bybit({
    'timeout': 10000,
    'enableRateLimit': True
})

now_time = bybit.iso8601(bybit.milliseconds())
print('交易所当前时间:', now_time, '   毫秒为', bybit.milliseconds())

# 加载市场数据
bybit_markets = bybit.load_markets()

# 获取k线数据
kline = getonedayklinedata(bybit, time202561)

high_point = 105320
float_width = 1000
low_point = high_point - float_width

high_buy = high_point + float_price
high_sell = high_point - float_price
low_buy = low_point + float_price
low_sell = low_point - float_price

have_position = 0
for kdata in reversed(kline):
    openPrice = float(kdata[1])  # 开盘价
    closePrice = float(kdata[4])  # 收盘价
    highPrice = float(kdata[2])  # 最高价
    lowPrice = float(kdata[3])  # 最低价
    volume = float(kdata[5])  # 交易量
    turnover = float(kdata[6])  # 交易额
    print('k线时间:', datetime.fromtimestamp(int(kdata[0]) / 1000), '开盘价', openPrice, '收盘价', closePrice, '最高价',
          highPrice, '最低价', lowPrice, '交易量', volume, '交易额', turnover)

    # 模拟一根k柱价格实时变动
    ktype = 'k柱是阳还是阴'
    # 阴柱
    if openPrice > closePrice:
        ktype = '阴'
        # 第一步从开盘价到最高价
        start_price = openPrice
        end_price = highPrice

        while start_price < highPrice:
            if start_price + 1 < highPrice:
                start_price = start_price + 1
            else:
                start_price = highPrice

            # print(start_price)

        # 第二步从最高价到最低价
        start_price = highPrice
        end_price = lowPrice

        while start_price > lowPrice:
            if start_price - 1 > lowPrice:
                start_price = start_price - 1
            else:
                start_price = lowPrice

            # print(start_price)

        # 第三步从最低价到收盘价
        start_price = lowPrice
        end_price = closePrice

        while start_price < closePrice:
            if start_price + 1 < closePrice:
                start_price = start_price + 1
            else:
                start_price = closePrice

            # print(start_price)


    else:
        ktype = '阳'
        # 第一步从开盘价到最低价
        start_price = openPrice
        end_price = lowPrice

        while start_price > lowPrice:
            if start_price - 1 > lowPrice:
                start_price = start_price - 1
            else:
                start_price = lowPrice

            # print(start_price)

        # 第二步从最低价到最高价
        start_price = lowPrice
        end_price = highPrice

        while start_price < highPrice:
            if start_price + 1 < highPrice:
                start_price = start_price + 1
            else:
                start_price = highPrice

            # print(start_price)

        # 第三步从最高价到收盘价
        start_price = highPrice
        end_price = closePrice

        while start_price > closePrice:
            if start_price - 1 > closePrice:
                start_price = start_price - 1
            else:
                start_price = closePrice

            # print(start_price)
