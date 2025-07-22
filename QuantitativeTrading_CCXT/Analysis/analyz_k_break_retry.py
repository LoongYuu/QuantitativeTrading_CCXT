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
float_price = 300  # 策略的加仓或平仓价格**********
min_amount = 0.001  # 此币最小下单数量************

category = 'linear'  # 合约
tra_side = 'Buy'  # 单向持仓策略，BUY为买，SELL为卖
tra_type = 'Market'  # 策略交易类型LIMIT/MARKET

all_amounts = 0  # 持仓数
loss_x = 0  # 亏损仓位
open_position_price = 0
charges = 0

high_point = 0
float_width = 1100
low_point = high_point - float_width
take_profit = float_width - 2 * float_price
break_try = 0

high_buy = high_point + float_price / 1.5
high_sell = high_point - float_price
low_buy = low_point + float_price
low_sell = low_point - float_price / 1.5

have_position = 0
position_status = ''
high_sell_status = 0
low_buy_status = 0


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


def process_data(price, now):
    global symbol, tra_amounts, float_price, min_amount, loss_x, all_amounts, open_position_price, charges
    global high_point, float_width, low_point, high_buy, high_sell, low_buy, low_sell, take_profit
    global have_position, position_status, high_sell_status, low_buy_status, max_x, max_time

    # 更新价格
    if price > high_point:
        high_point = price
        low_point = high_point - float_width
        high_sell = high_point - float_price
        low_buy = low_point + float_price
        high_sell_status = 1
        # low_buy_status = 0
    elif price < low_point:
        low_point = price
        high_point = low_point + float_width
        high_sell = high_point - float_price
        low_buy = low_point + float_price
        low_buy_status = 1
        # high_sell_status = 0

    # 没有仓位准备开仓********************************************************************
    if have_position == 0:
        # 做高多单
        if price > high_buy:
            # 检测下单数量的合法性
            qty = loss_x + tra_amounts
            if qty < min_amount:
                qty = min_amount
            order_params = {
                'category': category,
                'symbol': symbol,
                'side': 'Buy',
                'orderType': tra_type,
                'qty': str(qty),
            }
            order_res = create_order(price, order_params)
            open_position_price = price
            # 持仓增加
            all_amounts = all_amounts + qty

            # 标记为已经有仓位
            have_position = 1
            position_status = 'high_buy'

            print('没有仓位，突破新高做高多单!')
            print('   目前亏损', loss_x, '时间', now)
            print('   持仓', all_amounts, '类型', position_status, '价格', price)
        # 做低空单
        elif price < low_sell:
            # 检测下单数量的合法性
            qty = loss_x + tra_amounts
            if qty < min_amount:
                qty = min_amount
            order_params = {
                'category': category,
                'symbol': symbol,
                'side': 'Sell',
                'orderType': tra_type,
                'qty': str(qty),
            }
            order_res = create_order(price, order_params)
            open_position_price = price
            # 持仓增加
            all_amounts = all_amounts + qty

            # 标记为已经有仓位
            have_position = 1
            position_status = 'low_sell'

            print('没有仓位，突破新低做低空单!')
            print('   目前亏损', loss_x, '时间', now)
            print('   持仓', all_amounts, '类型', position_status, '价格', price)
        # 做高空单
        elif price < high_sell and high_sell_status == 1:
            # 开过单后重置状态
            high_sell_status = 0

            high_buy = high_point + float_price / 1.5
            # 检测下单数量的合法性
            qty = loss_x + tra_amounts
            if qty < min_amount:
                qty = min_amount
            order_params = {
                'category': category,
                'symbol': symbol,
                'side': 'Sell',
                'orderType': tra_type,
                'qty': str(qty),
            }
            order_res = create_order(price, order_params)
            open_position_price = price
            # 持仓增加
            all_amounts = all_amounts + qty

            # 标记为已经有仓位
            have_position = 1
            position_status = 'high_sell'

            print('没有仓位，突破新高折返做高空单!')
            print('   目前亏损', loss_x, '时间', now)
            print('   持仓', all_amounts, '类型', position_status, '价格', price)
        # 做低多单
        elif price > low_buy and low_buy_status == 1:
            # 开过单后重置状态
            low_buy_status = 0

            low_sell = low_point - float_price / 1.5
            # 检测下单数量的合法性
            qty = loss_x + tra_amounts
            if qty < min_amount:
                qty = min_amount
            order_params = {
                'category': category,
                'symbol': symbol,
                'side': 'Buy',
                'orderType': tra_type,
                'qty': str(qty),
            }
            order_res = create_order(price, order_params)
            open_position_price = price
            # 持仓增加
            all_amounts = all_amounts + qty

            # 标记为已经有仓位
            have_position = 1
            position_status = 'low_buy'

            print('没有仓位，突破新低折返做低多单!')
            print('   目前亏损', loss_x, '时间', now)
            print('   持仓', all_amounts, '类型', position_status, '价格', price)

    # 有仓位情况，分别讨论四种仓位种类*****************************************************************
    else:
        if position_status == 'high_buy':
            if price < high_sell:
                # 高点突破折返，开空单
                loss_x = loss_x + all_amounts * (open_position_price - price) / (float_price + charges)
                if loss_x < 0:
                    loss_x = 0
                if loss_x > max_x:
                    max_x = loss_x
                    max_time = now
                high_buy = high_point + float_price / 1.5
                # 检测下单数量的合法性
                qty = all_amounts + loss_x + tra_amounts
                if qty < min_amount:
                    qty = min_amount
                order_params = {
                    'category': category,
                    'symbol': symbol,
                    'side': 'Sell',
                    'orderType': tra_type,
                    'qty': str(qty),
                }
                order_res = create_order(price, order_params)
                open_position_price = price
                # 仓位翻倍
                all_amounts = loss_x + tra_amounts

                # 手上是空单
                have_position = 1
                position_status = 'high_sell'

                print('有仓位，突破新高折返做高空单!')
                print('   目前亏损', loss_x, '时间', now)
                print('   持仓', all_amounts, '类型', position_status, '价格', price)

            elif price > open_position_price + take_profit and loss_x > 0:
                # 有亏损直接止盈
                loss_x = 0
                high_buy = high_point + float_price / 1.5
                # 检测下单数量的合法性
                qty = all_amounts
                if qty < min_amount:
                    qty = min_amount
                order_params = {
                    'category': category,
                    'symbol': symbol,
                    'side': 'Sell',
                    'orderType': tra_type,
                    'qty': str(qty),
                }
                order_res = create_order(price, order_params)
                open_position_price = price
                # 仓位0
                all_amounts = 0

                # 手上没单
                have_position = 0
                position_status = ''

                print('有仓位，突破新高止盈!!!!!')
                print('   目前亏损', loss_x, '时间', now)
                print('   持仓', all_amounts, '类型', position_status, '价格', price)
        elif position_status == 'high_sell':
            if price == high_point:
                # 打损高空单

                loss_x = loss_x + all_amounts
                if loss_x > max_x:
                    max_x = loss_x
                    max_time = now
                # 检测下单数量的合法性
                qty = all_amounts
                if qty < min_amount:
                    qty = min_amount
                order_params = {
                    'category': category,
                    'symbol': symbol,
                    'side': 'Buy',
                    'orderType': tra_type,
                    'qty': str(qty),
                }
                order_res = create_order(price, order_params)
                open_position_price = price
                # 仓位清零
                all_amounts = 0

                # 手上没有单
                have_position = 0
                position_status = ''

                print('有仓位，高空单被打损，准备突破新高!')
                print('   目前亏损', loss_x, '时间', now)
                print('   持仓', all_amounts, '类型', position_status, '价格', price)

            elif price < low_buy:
                # 直接止盈

                loss_x = 0
                if loss_x > max_x:
                    max_x = loss_x
                    max_time = now
                # 检测下单数量的合法性
                qty = all_amounts
                if qty < min_amount:
                    qty = min_amount
                order_params = {
                    'category': category,
                    'symbol': symbol,
                    'side': 'Buy',
                    'orderType': tra_type,
                    'qty': str(qty),
                }
                order_res = create_order(price, order_params)

                # 仓位为0
                all_amounts = 0

                # 手上没单
                have_position = 0
                position_status = ''

                print('有仓位，高空单止盈!!!!!!!!')
                print('   目前亏损', loss_x, '时间', now)
                print('   持仓', all_amounts, '类型', position_status, '价格', price)
        elif position_status == 'low_sell':
            if price > low_buy:
                # 低点突破折返，开多单
                loss_x = loss_x + all_amounts * (price - open_position_price) / (float_price + charges)
                if loss_x < 0:
                    loss_x = 0
                if loss_x > max_x:
                    max_x = loss_x
                    max_time = now
                low_sell = low_point - float_price / 1.5
                # 检测下单数量的合法性
                qty = all_amounts + loss_x + tra_amounts
                if qty < min_amount:
                    qty = min_amount
                order_params = {
                    'category': category,
                    'symbol': symbol,
                    'side': 'Buy',
                    'orderType': tra_type,
                    'qty': str(qty),
                }
                order_res = create_order(price, order_params)
                open_position_price = price
                # 仓位翻倍
                all_amounts = loss_x + tra_amounts

                # 手上是多单
                have_position = 1
                position_status = 'low_buy'

                print('有仓位，突破新低折返做低多单!')
                print('   目前亏损', loss_x, '时间', now)
                print('   持仓', all_amounts, '类型', position_status, '价格', price)

            elif price < open_position_price - take_profit and loss_x > 0:
                # 有亏损直接止盈
                loss_x = 0
                low_sell = low_point - float_price / 1.5
                # 检测下单数量的合法性
                qty = all_amounts
                if qty < min_amount:
                    qty = min_amount
                order_params = {
                    'category': category,
                    'symbol': symbol,
                    'side': 'Buy',
                    'orderType': tra_type,
                    'qty': str(qty),
                }
                order_res = create_order(price, order_params)
                open_position_price = price
                # 仓位0
                all_amounts = 0

                # 手上没单
                have_position = 0
                position_status = ''

                print('有仓位，突破新低止盈!!!!!')
                print('   目前亏损', loss_x, '时间', now)
                print('   持仓', all_amounts, '类型', position_status, '价格', price)

        elif position_status == 'low_buy':
            if price == low_point:
                # 打损低多单

                loss_x = loss_x + all_amounts
                if loss_x > max_x:
                    max_x = loss_x
                    max_time = now
                # 检测下单数量的合法性
                qty = all_amounts
                if qty < min_amount:
                    qty = min_amount
                order_params = {
                    'category': category,
                    'symbol': symbol,
                    'side': 'Sell',
                    'orderType': tra_type,
                    'qty': str(qty),
                }
                order_res = create_order(price, order_params)
                open_position_price = price
                # 仓位清零
                all_amounts = 0

                # 手上没有单
                have_position = 0
                position_status = ''

                print('有仓位，低多单被打损，准备突破新低!')
                print('   目前亏损', loss_x, '时间', now)
                print('   持仓', all_amounts, '类型', position_status, '价格', price)

            elif price > high_sell:
                # 破新高并到高空点位
                loss_x = 0
                if loss_x > max_x:
                    max_x = loss_x
                    max_time = now
                # 检测下单数量的合法性
                qty = all_amounts
                if qty < min_amount:
                    qty = min_amount
                order_params = {
                    'category': category,
                    'symbol': symbol,
                    'side': 'Sell',
                    'orderType': tra_type,
                    'qty': str(qty),
                }
                order_res = create_order(price, order_params)

                # 仓位为0
                all_amounts = 0

                # 手上没单
                have_position = 0
                position_status = ''

                print('有仓位，低多单止盈!!!!!!!!')
                print('   目前亏损', loss_x, '时间', now)
                print('   持仓', all_amounts, '类型', position_status, '价格', price)


oneday = 24 * 60 * 60
time202561 = 1748707200 + oneday * -30
end_time = 1748707200

bybit = ccxt.bybit({
    'timeout': 10000,
    'enableRateLimit': True
})

now_time = bybit.iso8601(bybit.milliseconds())
print('交易所当前时间:', now_time, '   毫秒为', bybit.milliseconds())

# 加载市场数据
bybit_markets = bybit.load_markets()

while time202561 < end_time:
    param = {
        'category': category,
        'symbol': symbol,
        'interval': '3',  # 时间颗粒度3分钟
        'limit': '1000',  # 每页数量限制
        'end': (time202561 + oneday) * 1000 - 1,
        'start': time202561 * 1000,
    }

    kline = bybit.public_get_v5_market_kline(params=param)

    for kdata in reversed(kline['result']['list']):
        openPrice = float(kdata[1])  # 开盘价
        closePrice = float(kdata[4])  # 收盘价
        highPrice = float(kdata[2])  # 最高价
        lowPrice = float(kdata[3])  # 最低价
        volume = float(kdata[5])  # 交易量
        turnover = float(kdata[6])  # 交易额
        ktime = datetime.fromtimestamp(int(kdata[0]) / 1000)
        # print('k线时间:', datetime.fromtimestamp(int(kdata[0])/1000), '开盘价', openPrice, '收盘价', closePrice, '最高价', highPrice, '最低价', lowPrice, '交易量', volume, '交易额', turnover)

        # 模拟一根k柱价格实时变动
        ktype = 'k柱是阳还是阴'
        float_uni = 0.5
        # 阴柱
        if openPrice > closePrice:
            ktype = '阴'
            # 第一步从开盘价到最高价
            start_price = openPrice
            end_price = highPrice

            while start_price < highPrice:
                if start_price + float_uni < highPrice:
                    start_price = start_price + float_uni
                else:
                    start_price = highPrice

                process_data(start_price, ktime)

            # 第二步从最高价到最低价
            start_price = highPrice
            end_price = lowPrice

            while start_price > lowPrice:
                if start_price - float_uni > lowPrice:
                    start_price = start_price - float_uni
                else:
                    start_price = lowPrice

                process_data(start_price, ktime)

            # 第三步从最低价到收盘价
            start_price = lowPrice
            end_price = closePrice

            while start_price < closePrice:
                if start_price + float_uni < closePrice:
                    start_price = start_price + float_uni
                else:
                    start_price = closePrice

                process_data(start_price, ktime)


        else:
            ktype = '阳'
            # 第一步从开盘价到最低价
            start_price = openPrice
            end_price = lowPrice

            while start_price > lowPrice:
                if start_price - float_uni > lowPrice:
                    start_price = start_price - float_uni
                else:
                    start_price = lowPrice

                process_data(start_price, ktime)

            # 第二步从最低价到最高价
            start_price = lowPrice
            end_price = highPrice

            while start_price < highPrice:
                if start_price + float_uni < highPrice:
                    start_price = start_price + float_uni
                else:
                    start_price = highPrice

                process_data(start_price, ktime)

            # 第三步从最高价到收盘价
            start_price = highPrice
            end_price = closePrice

            while start_price > closePrice:
                if start_price - float_uni > closePrice:
                    start_price = start_price - float_uni
                else:
                    start_price = closePrice

                process_data(start_price, ktime)

    time202561 = time202561 + oneday

print('账户最终余额', account_money)
print('结束时还有合约张数：', account_coin)
print('最大亏损张数', max_x, '时间', max_time)
print('共产生手续费', charge_fee)
