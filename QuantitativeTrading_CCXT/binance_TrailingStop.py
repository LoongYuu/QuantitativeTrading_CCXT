import ccxt
from datetime import datetime
import logging
import time
import json
# 策略简介：
# 买涨或买跌，设定涨加或亏平，持续更新价格进行平仓或加仓操作
# 每次更新当前价格，若胜利，则看目前有没有加仓:若没有加仓需根据x来执行加仓或更新下个目标，若加仓了则需要只保留底仓并重新设置目标止损
#               若失败需要切换做单方向重新下初始单,看目前有没有加仓:若没有加仓则等待止损单完成增加x即可，若加仓了需要更新y为截至目前的全部亏损等待加仓止损单完成。
# 4: 追踪点位,及时止损,智能计算损失仓位，避免盲目翻仓
# 配置日志记录
logging.basicConfig(
    filename='binance_trading_errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


# 定义重试装饰器（可选，用于封装重试逻辑）
def retry(max_retries=3, delay=5):
    def decorator(func):
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                # 交易所请求超时重试，先要捕获子类
                except ccxt.RequestTimeout as e:
                    wait_time = delay * (attempt + 1)
                    print(f"请求超时，重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒...")
                    time.sleep(wait_time)
                except ccxt.NetworkError as e:
                    wait_time = delay * (attempt + 1)
                    print(f"网络错误，重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒...")
                    time.sleep(wait_time)
                except ccxt.BaseError as e:
                    # 尝试解析错误代码
                    error_code = None
                    try:
                        raw_message = e.args[0]  # e.args 是一个 tuple
                        if isinstance(raw_message, str) and '{' in raw_message:
                            error_data = json.loads(raw_message.split('binance')[-1].strip())
                            error_code = error_data.get('code')
                            # 输出解析出的错误码,是int
                            # print(error_code)
                    except Exception as parse_err:
                        logging.error(f"错误解析失败: {parse_err}")

                    # 根据不同错误码处理错误
                    if error_code == -1008 and attempt < max_retries - 1:
                        wait_time = delay * (attempt + 1)
                        logging.warning(f"服务器过载（code -1008），重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒...")
                        print(f"服务器过载（code -1008），重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒...")
                        time.sleep(wait_time)
                    else:
                        logging.error(f"操作失败：{e}")
                        raise

        return wrapper
    return decorator


# 查询合约指定币对价格
@retry(max_retries=100, delay=2)  # 最大重试100次，初始延迟2秒
def fetch_ticker_price(exchange, para_symbol):
    return exchange.fapipublic_get_ticker_price({'symbol': para_symbol})


# 合约下单
@retry(max_retries=100, delay=2)
def create_order(exchange, params):
    return exchange.fapiPrivatePostOrder(params)


if __name__ == '__main__':

    symbol = 'SUIUSDC'  # 要交易的币种************
    tra_amounts = 10.0  # 底仓数量*************
    float_price = 0.03  # 策略的加仓或平仓价格**********
    price_PRECISION = 4  # 此币的价格精度,小数点后几位**********
    min_amount = 2  # 此币最小下单数量************

    tra_side = 'BUY'  # 单向持仓策略，BUY为买，SELL为卖
    tra_type = 'MARKET'  # 策略交易类型LIMIT/MARKET

    tra_price = 0.0  # 成交价格
    all_amounts = 0  # 持仓数
    loss_x = 0  # 亏损仓位
    win_price = 0  # 成功价格
    loss_price = 0  # 失败价格
    have_plus_loss = 0  # 是否添加了亏损仓位
    win_rate = 1.5  # 成功的倍率******************
    charges = float_price * 0.1  # 智能加仓减仓手续费************

    track_price_extremes = 0  # 追踪高低点,检测价格极限
    record_stop = 0  # 智能计算止损损失的仓位

    print('交易对:', symbol)
    print('底仓数量:', tra_amounts)
    print('单位浮动价格:', float_price)
    print('价格精度:', price_PRECISION)

    # 账号信息
    binance = ccxt.binance({
        'apiKey': 'sPoEmUsWxgt6YxmhH00Dtmom86oGytYsFOHgbc4mlhxDD1lfQUg6LWYNNvmbu8b7',
        'secret': 'w7tZ8vAMIiIsTNu5lxD2rp0jFqroLVuFRWTpXnfpW8hQYl893sGZ8bZbwbCaZxHQ',
        'timeout': 10000,
        'enableRateLimit': True
    })
    print('交易所当前时间:', binance.iso8601(binance.milliseconds()))

    # 加载市场数据
    binance_markets = binance.load_markets()

    # 调整开仓杠杆,逐全仓模式,输出资金信息,可在app上完成,机器会默认app上的状态

    # 进入策略,永不结束
    while True:

        # 获取行情数据（自动重试）
        ticker_data = fetch_ticker_price(binance, symbol)
        tra_price = float(ticker_data['price'])

        # 更新目标点位,头仓按照追踪价格只需0.5f
        if tra_side == 'BUY':
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

        # 初始单信息
        print('初始点位更新成功!', '时间:', datetime.now())
        print('价格:', tra_price, '   方向:', tra_side, '   目前亏损张数x:', loss_x)

        i = 0
        while i == 0:
            # 实时获取价格（自动重试）
            ticker_data = fetch_ticker_price(binance, symbol)
            price = float(ticker_data['price'])
            # print('价格:', price, '时间:' + binance.iso8601(binance.milliseconds()))

            # 追踪高低点,更新时连带更新止损点
            if tra_side == 'BUY':
                if price > track_price_extremes:
                    track_price_extremes = price
                    loss_price = track_price_extremes - float_price
            elif tra_side == 'SELL':
                if price < track_price_extremes:
                    track_price_extremes = price
                    loss_price = track_price_extremes + float_price

            # 仓位管理,如果做多
            if tra_side == 'BUY':
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
                            quantity = tra_amounts
                            if quantity < min_amount:
                                quantity = min_amount
                            order_params = {
                                'symbol': symbol,
                                'side': tra_side,
                                'type': tra_type,
                                'quantity': quantity
                            }
                            order_res = create_order(binance, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)

                            all_amounts = all_amounts + quantity

                            # 信息
                            print('   胜利！目前无亏损，追加了仓位:', quantity)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                        # 有亏损，加亏损仓并更改标记
                        elif loss_x != 0:
                            quantity = loss_x + tra_amounts
                            if quantity < min_amount:
                                quantity = min_amount
                            order_params = {
                                'symbol': symbol,
                                'side': tra_side,
                                'type': tra_type,
                                'quantity': quantity
                            }
                            order_res = create_order(binance, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)

                            all_amounts = all_amounts + quantity
                            have_plus_loss = 1

                            # 信息
                            print('   胜利！有亏损，追加了仓位:', quantity)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                    # 已经添加了亏损仓
                    else:
                        # 止盈亏损仓，将亏损设置为0,并设置没有添加亏损,在添加一份底仓
                        if loss_x > tra_amounts:
                            quantity = loss_x - tra_amounts
                            if quantity < min_amount:
                                quantity = min_amount
                            order_params = {
                                'symbol': symbol,
                                'side': 'SELL',
                                'type': tra_type,
                                'quantity': quantity
                            }
                            order_res = create_order(binance, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)
                            all_amounts = all_amounts - quantity
                        elif loss_x < tra_amounts:
                            quantity = tra_amounts - loss_x
                            if quantity < min_amount:
                                quantity = min_amount
                            order_params = {
                                'symbol': symbol,
                                'side': 'BUY',
                                'type': tra_type,
                                'quantity': quantity
                            }
                            order_res = create_order(binance, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)
                            all_amounts = all_amounts + quantity

                        have_plus_loss = 0

                        # 信息
                        print('   胜利中的胜利！已平亏损仓位:', loss_x, '   再次追加：', tra_amounts)
                        print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                        loss_x = 0

                # 价格小于失败价
                elif price < loss_price:
                    # 失败了，清仓改方向
                    tra_side = 'SELL'
                    # 清仓等待下次机会
                    if all_amounts != 0:
                        quantity = all_amounts
                        if quantity < min_amount:
                            quantity = min_amount
                        order_params = {
                            'symbol': symbol,
                            'side': 'SELL',
                            'type': tra_type,
                            'quantity': quantity
                        }
                        order_res = create_order(binance, order_params)
                        # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                        time.sleep(2)

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
                    loss_x = loss_x - int((loss_price - record_stop) * all_amounts / (float_price + charges))
                    if loss_x < 0:
                        loss_x = 0

                    # 已清仓
                    all_amounts = 0

                    i = 1  # break

            elif tra_side == 'SELL':
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
                            quantity = tra_amounts
                            if quantity < min_amount:
                                quantity = min_amount
                            order_params = {
                                'symbol': symbol,
                                'side': tra_side,
                                'type': tra_type,
                                'quantity': quantity
                            }
                            order_res = create_order(binance, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)

                            all_amounts = all_amounts + quantity

                            # 信息
                            print('   胜利！目前无亏损，追加了仓位:', quantity)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                        # 有亏损，加亏损仓并更改标记
                        elif loss_x != 0:
                            quantity = loss_x + tra_amounts
                            if quantity < min_amount:
                                quantity = min_amount
                            order_params = {
                                'symbol': symbol,
                                'side': tra_side,
                                'type': tra_type,
                                'quantity': quantity
                            }
                            order_res = create_order(binance, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)

                            all_amounts = all_amounts + quantity
                            have_plus_loss = 1

                            # 信息
                            print('   胜利！有亏损，追加了仓位:', quantity)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                    # 已经添加了亏损仓
                    else:
                        # 止盈亏损仓,将亏损设置为0，并设置没有添加亏损,在添加一份底仓
                        if loss_x > tra_amounts:
                            quantity = loss_x - tra_amounts
                            if quantity < min_amount:
                                quantity = min_amount
                            order_params = {
                                'symbol': symbol,
                                'side': 'BUY',
                                'type': tra_type,
                                'quantity': quantity
                            }
                            order_res = create_order(binance, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)
                            all_amounts = all_amounts - quantity
                        elif loss_x < tra_amounts:
                            quantity = tra_amounts - loss_x
                            if quantity < min_amount:
                                quantity = min_amount
                            order_params = {
                                'symbol': symbol,
                                'side': 'SELL',
                                'type': tra_type,
                                'quantity': quantity
                            }
                            order_res = create_order(binance, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)
                            all_amounts = all_amounts + quantity

                        have_plus_loss = 0

                        # 信息
                        print('   胜利中的胜利！已平亏损仓位:', loss_x, '   再次追加：', tra_amounts)
                        print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                        loss_x = 0

                # 价格大于失败价
                elif price > loss_price:
                    # 失败了，清仓改方向
                    tra_side = 'BUY'
                    # 清仓等待下次机会
                    if all_amounts != 0:
                        quantity = all_amounts
                        if quantity < min_amount:
                            quantity = min_amount
                        order_params = {
                            'symbol': symbol,
                            'side': 'BUY',
                            'type': tra_type,
                            'quantity': quantity
                        }
                        order_res = create_order(binance, order_params)
                        # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                        time.sleep(2)

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
                    loss_x = loss_x - int((record_stop - loss_price) * all_amounts / (float_price + charges))
                    if loss_x < 0:
                        loss_x = 0

                    # 已清仓
                    all_amounts = 0

                    i = 1  # break
