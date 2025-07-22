import ccxt
from datetime import datetime

# 模拟账户
account_money = 60000
account_coin = 0
charge_fee = 0

symbol = 'BTCUSDT'  # 要交易的币种************
tra_amounts = 0.001  # 底仓数量*************
float_price = 3200  # 策略的加仓或平仓价格**********
price_PRECISION = 2  # 此币的价格精度,小数点后几位**********
min_amount = 0.001  # 此币最小下单数量************

category = 'linear'  # 合约
tra_side = 'Buy'  # 单向持仓策略，BUY为买，SELL为卖
tra_type = 'Market'  # 策略交易类型LIMIT/MARKET

all_amounts = 0  # 持仓数
tra_price = 0.0  # 成交价格
loss_x = 0  # 亏损仓位cha
win_price = 0  # 成功价格
loss_price = 0  # 失败价格
have_plus_loss = 0  # 是否添加了亏损仓位
win_rate = 1.5  # 成功的倍率******************
charges = 100  # 智能加仓减仓手续费************
amount_PRECISION = 3

track_price_extremes = 0  # 追踪高低点,检测价格极限
record_stop = 0  # 智能计算止损损失的仓位
i = 1
max_x = 0
max_time = 0


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


def first_start(price, now):
    global symbol, tra_amounts, float_price, price_PRECISION, min_amount, category, tra_side, tra_type
    global all_amounts, tra_price, loss_x, win_price, loss_price, have_plus_loss, win_rate, charges
    global track_price_extremes, record_stop, i, amount_PRECISION, max_x, max_time
    # 获取行情数据（自动重试）
    tra_price = price

    # 更新目标点位,头仓按照追踪价格只需0.5f
    if tra_side == 'Buy':
        win_price = tra_price + float_price * (win_rate - 1)
        loss_price = tra_price - float_price
        record_stop = loss_price
    else:
        win_price = tra_price - float_price * (win_rate - 1)
        loss_price = tra_price + float_price
        record_stop = loss_price

    # 此时全部仓位应是0
    all_amounts = 0

    # 追踪点位从头仓点位开始
    track_price_extremes = tra_price

    i = 0

    # 初始单信息
    print('初始点位更新成功!', '时间:', now)
    print('价格:', tra_price, '   方向:', tra_side, '   目前亏损张数x:', loss_x)


def process_data(price, now):
    global symbol, tra_amounts, float_price, price_PRECISION, min_amount, category, tra_side, tra_type
    global all_amounts, tra_price, loss_x, win_price, loss_price, have_plus_loss, win_rate, charges
    global track_price_extremes, record_stop, i, amount_PRECISION, max_x, max_time
    # 追踪高低点,更新时连带更新止损点
    if tra_side == 'Buy':
        if price > track_price_extremes:
            track_price_extremes = price
            loss_price = track_price_extremes - float_price
    elif tra_side == 'Sell':
        if price < track_price_extremes:
            track_price_extremes = price
            loss_price = track_price_extremes + float_price

    # 仓位管理,如果做多
    if tra_side == 'Buy':
        # 价格大于获胜价
        if price > win_price:
            # 更新下个目标,并讨论有没有亏损仓
            win_price = win_price + float_price * win_rate
            # 止损按照动态开单价格
            loss_price = price - float_price
            record_stop = loss_price

            # 没有添加亏损仓
            if have_plus_loss == 0:
                # 没有亏损,相当于在这里开了底仓
                if loss_x == 0:
                    # 检测下单数量的合法性
                    qty = tra_amounts
                    if qty < min_amount:
                        qty = min_amount
                    order_params = {
                        'category': category,
                        'symbol': symbol,
                        'side': tra_side,
                        'orderType': tra_type,
                        'qty': str(qty),
                    }
                    order_res = create_order(price, order_params)
                    # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍

                    all_amounts = all_amounts + qty

                    # 信息
                    print('   胜利！目前无亏损，追加了仓位:', qty)
                    print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                # 有亏损，加亏损仓并更改标记
                elif loss_x != 0:
                    qty = loss_x + tra_amounts
                    if qty < min_amount:
                        qty = min_amount
                    order_params = {
                        'category': category,
                        'symbol': symbol,
                        'side': tra_side,
                        'orderType': tra_type,
                        'qty': str(qty)
                    }
                    order_res = create_order(price, order_params)
                    # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍

                    all_amounts = all_amounts + qty
                    have_plus_loss = 1

                    # 信息
                    print('   胜利！有亏损，追加了仓位:', qty)
                    print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

            # 已经添加了亏损仓
            else:
                # 止盈亏损仓，将亏损设置为0,并设置没有添加亏损,在添加一份底仓
                if loss_x > tra_amounts:
                    qty = loss_x - tra_amounts
                    if qty < min_amount:
                        qty = min_amount
                    order_params = {
                        'category': category,
                        'symbol': symbol,
                        'side': 'Sell',
                        'orderType': tra_type,
                        'qty': str(qty)
                    }
                    order_res = create_order(price, order_params)
                    # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                    all_amounts = all_amounts - qty
                elif loss_x < tra_amounts:
                    qty = tra_amounts - loss_x
                    if qty < min_amount:
                        qty = min_amount
                    order_params = {
                        'category': category,
                        'symbol': symbol,
                        'side': 'Buy',
                        'orderType': tra_type,
                        'qty': str(qty)
                    }
                    order_res = create_order(price, order_params)
                    # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                    all_amounts = all_amounts + qty

                have_plus_loss = 0

                # 信息
                print('   胜利中的胜利！已平亏损仓位:', loss_x, '   再次追加：', tra_amounts)
                print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                loss_x = 0

        # 价格小于失败价
        elif price < loss_price:
            # 失败了，清仓改方向
            tra_side = 'Sell'
            # 清仓等待下次机会
            if all_amounts != 0:
                qty = all_amounts
                if qty < min_amount:
                    qty = min_amount
                order_params = {
                    'category': category,
                    'symbol': symbol,
                    'side': tra_side,
                    'orderType': tra_type,
                    'qty': str(qty)
                }
                order_res = create_order(price, order_params)
                # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍

            # 如果没有添加亏损仓
            if have_plus_loss == 0:
                if all_amounts == 0:
                    # 信息
                    print('  失败！没有仓位!')
                else:
                    # x应累加最后一个底仓
                    loss_x = loss_x + tra_amounts
                    print('  失败！将最后一个仓位添加到亏损！')

            # 如果添加了亏损仓
            elif have_plus_loss == 1:
                # 信息
                print('  失败中的失败！亏损翻倍')
                # 叠加亏损
                loss_x = loss_x + all_amounts
                have_plus_loss = 0

            # 智能加亏损仓
            adjustment = (loss_price - record_stop) * all_amounts / (float_price + charges)

            loss_x = loss_x - adjustment
            # 舍弃到交易所允许的精度范围
            loss_x = round(loss_x, amount_PRECISION)

            if loss_x < 0:
                loss_x = 0
            if loss_x > 100:
                loss_x = 0

            if loss_x > max_x:
                max_x = loss_x
                max_time = now

            # 已清仓
            all_amounts = 0

            i = 1  # need first start

    elif tra_side == 'Sell':
        # 价格小于获胜价，胜利
        if price < win_price:
            # 更新下个目标,并讨论有没有亏损仓
            win_price = win_price - float_price * win_rate
            # 止损按照动态开单价格
            loss_price = price + float_price
            record_stop = loss_price

            # 没有添加亏损仓
            if have_plus_loss == 0:
                # 没有亏损,相当于在这里开了底仓
                if loss_x == 0:
                    qty = tra_amounts
                    if qty < min_amount:
                        qty = min_amount
                    order_params = {
                        'category': category,
                        'symbol': symbol,
                        'side': tra_side,
                        'orderType': tra_type,
                        'qty': str(qty)
                    }
                    order_res = create_order(price, order_params)
                    # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍

                    all_amounts = all_amounts + qty

                    # 信息
                    print('   胜利！目前无亏损，追加了仓位:', qty)
                    print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                # 有亏损，加亏损仓并更改标记
                elif loss_x != 0:
                    qty = loss_x + tra_amounts
                    if qty < min_amount:
                        qty = min_amount
                    order_params = {
                        'category': category,
                        'symbol': symbol,
                        'side': tra_side,
                        'orderType': tra_type,
                        'qty': str(qty)
                    }
                    order_res = create_order(price, order_params)
                    # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍

                    all_amounts = all_amounts + qty
                    have_plus_loss = 1

                    # 信息
                    print('   胜利！有亏损，追加了仓位:', qty)
                    print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

            # 已经添加了亏损仓
            else:
                # 止盈亏损仓,将亏损设置为0，并设置没有添加亏损,在添加一份底仓
                if loss_x > tra_amounts:
                    qty = loss_x - tra_amounts
                    if qty < min_amount:
                        qty = min_amount
                    order_params = {
                        'category': category,
                        'symbol': symbol,
                        'side': 'Buy',
                        'orderType': tra_type,
                        'qty': str(qty)
                    }
                    order_res = create_order(price, order_params)
                    # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                    all_amounts = all_amounts - qty
                elif loss_x < tra_amounts:
                    qty = tra_amounts - loss_x
                    if qty < min_amount:
                        qty = min_amount
                    order_params = {
                        'category': category,
                        'symbol': symbol,
                        'side': 'Sell',
                        'orderType': tra_type,
                        'qty': str(qty)
                    }
                    order_res = create_order(price, order_params)
                    all_amounts = all_amounts + qty

                have_plus_loss = 0

                # 信息
                print('   胜利中的胜利！已平亏损仓位:', loss_x, '   再次追加：', tra_amounts)
                print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                loss_x = 0

        # 价格大于失败价
        elif price > loss_price:
            # 失败了，清仓改方向
            tra_side = 'Buy'
            # 清仓等待下次机会
            if all_amounts != 0:
                qty = all_amounts
                if qty < min_amount:
                    qty = min_amount
                order_params = {
                    'category': category,
                    'symbol': symbol,
                    'side': tra_side,
                    'orderType': tra_type,
                    'qty': str(qty)
                }
                order_res = create_order(price, order_params)

            # 如果没有添加亏损仓
            if have_plus_loss == 0:
                if all_amounts == 0:
                    # 信息
                    print('  失败！没有仓位!')
                else:
                    # x应累加最后一个底仓
                    loss_x = loss_x + tra_amounts
                    print('  失败！将最后一个仓位添加到亏损！')

            # 如果添加了亏损仓
            elif have_plus_loss == 1:
                # 信息
                print('  失败中的失败！亏损翻倍')
                # 叠加亏损
                loss_x = loss_x + all_amounts
                have_plus_loss = 0

            # 智能加亏损仓,(移动止损前止损价格：record_stop - 止损单实际成交点位loss_price) * 持仓数 / 一个波动单位价格
            adjustment = (record_stop - loss_price) * all_amounts / (float_price + charges)

            loss_x = loss_x - adjustment
            # 舍弃到交易所允许的精度范围
            loss_x = round(loss_x, amount_PRECISION)
            if loss_x < 0:
                loss_x = 0
            if loss_x > 100:
                loss_x = 0

            if loss_x > max_x:
                max_x = loss_x
                max_time = now

            # 已清仓
            all_amounts = 0

            i = 1  # need first start


oneday = 24 * 60 * 60
time202561 = 1748707200 + oneday * -360
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

                if i == 1:
                    first_start(start_price, ktime)
                process_data(start_price, ktime)

            # 第二步从最高价到最低价
            start_price = highPrice
            end_price = lowPrice

            while start_price > lowPrice:
                if start_price - float_uni > lowPrice:
                    start_price = start_price - float_uni
                else:
                    start_price = lowPrice

                if i == 1:
                    first_start(start_price, ktime)
                process_data(start_price, ktime)

            # 第三步从最低价到收盘价
            start_price = lowPrice
            end_price = closePrice

            while start_price < closePrice:
                if start_price + float_uni < closePrice:
                    start_price = start_price + float_uni
                else:
                    start_price = closePrice

                if i == 1:
                    first_start(start_price, ktime)
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

                if i == 1:
                    first_start(start_price, ktime)
                process_data(start_price, ktime)

            # 第二步从最低价到最高价
            start_price = lowPrice
            end_price = highPrice

            while start_price < highPrice:
                if start_price + float_uni < highPrice:
                    start_price = start_price + float_uni
                else:
                    start_price = highPrice

                if i == 1:
                    first_start(start_price, ktime)
                process_data(start_price, ktime)

            # 第三步从最高价到收盘价
            start_price = highPrice
            end_price = closePrice

            while start_price > closePrice:
                if start_price - float_uni > closePrice:
                    start_price = start_price - float_uni
                else:
                    start_price = closePrice

                if i == 1:
                    first_start(start_price, ktime)
                process_data(start_price, ktime)

    time202561 = time202561 + oneday

print('账户最终余额', account_money)
print('结束时还有合约张数：', account_coin)
print('最大亏损张数', max_x, '时间', max_time)
print('共产生手续费', charge_fee)
