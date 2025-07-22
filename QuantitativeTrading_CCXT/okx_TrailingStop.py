import ccxt
from datetime import datetime
import logging
import time
import json
import re
# 策略简介：
# 买涨或买跌，设定涨加或亏平，持续更新价格进行平仓或加仓操作
# 每次更新当前价格，若胜利，则看目前有没有加仓:若没有加仓需根据x来执行加仓或更新下个目标，若加仓了则需要只保留底仓并重新设置目标止损
#               若失败需要切换做单方向重新下初始单,看目前有没有加仓:若没有加仓则等待止损单完成增加x即可，若加仓了需要更新y为截至目前的全部亏损等待加仓止损单完成。
# 4: 追踪点位,及时止损,智能计算损失仓位，避免盲目翻仓
# 配置日志记录
logging.basicConfig(
    filename='okx_trading_errors.log',
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
                except ccxt.RateLimitExceeded as e:
                    wait_time = 0.5
                    print(f"请求超时，重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                    time.sleep(wait_time)
                except ccxt.ExchangeNotAvailable as e:
                    # 专门处理502错误（服务器临时不可用）
                    if "502 Bad Gateway" in str(e):
                        wait_time = delay * (attempt + 1) * 2  # 等待时间加倍
                        print(f"502错误：交易所服务器暂时不可用，等待 {wait_time} 秒后重试")
                        time.sleep(wait_time)
                    else:
                        raise  # 其他ExchangeNotAvailable错误继续抛出
                except ccxt.RequestTimeout as e:
                    wait_time = delay * (attempt + 1)
                    print(f"请求超时，重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                    time.sleep(wait_time)
                except ccxt.NetworkError as e:
                    wait_time = delay * (attempt + 1)
                    print(f"网络错误，重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒...")
                    time.sleep(wait_time)
                except ccxt.BaseError as e:
                    # 解析错误码（使用正则表达式方案）
                    error_code = parse_error_code(e)
                    # print('错误码', error_code, type(error_code))
                    error_code = int(error_code)

                    # 处理可重试的错误（如服务器过载、超时等）
                    if error_code in [50001, 50013] and attempt < max_retries - 1:
                        wait_time = delay * (attempt + 1)
                        logging.warning(f"错误码 {error_code}，当前系统繁忙，请稍后重试！重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                        print(f"错误码 {error_code}，当前系统繁忙，请稍后重试！重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                        time.sleep(wait_time)
                    elif error_code == 50026 and attempt < max_retries - 1:
                        wait_time = delay * (attempt + 1)
                        logging.warning(f"错误码 {error_code}，系统错误，请稍后重试！重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                        print(f"错误码 {error_code}，系统错误，请稍后重试！重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                        time.sleep(wait_time)
                    else:
                        logging.error(f"操作失败：{e}")
                        raise

        return wrapper

    return decorator


# 错误码解析函数（正则方案）
def parse_error_code(e):
    raw_message = str(e)
    match = re.search(r'okx\s*[:]?\s*({.*})', raw_message)
    if match:
        json_str = match.group(1)
        try:
            return json.loads(json_str).get('code')
        except json.JSONDecodeError:
            return None
    return None


# 查询合约指定币对价格
@retry(max_retries=100, delay=2)  # 最大重试100次，初始延迟2秒
def fetch_ticker_price(exchange, para_symbol, para_instType):
    return exchange.public_get_public_mark_price({'uly': para_symbol, 'instType': para_instType})


# 合约下单
@retry(max_retries=100, delay=2)
def create_order(exchange, params):
    return exchange.private_post_trade_order(params)


if __name__ == '__main__':

    # 交易类型
    symbol = 'WCT-USDT'  # 要交易的币种************
    tra_amounts = 5  # 底仓数量,对欧意这个币来说1是10*************
    float_price = 0.006  # 策略的加仓或平仓价格**********
    price_PRECISION = 4  # 此币的价格精度,小数点后几位**********
    min_amount = 1  # 此币最小下单数量************

    instId = 'WCT-USDT-SWAP'  # 下单的合约信息**************
    instType = 'SWAP'  # 永续合约
    tdMode = 'cross'  # 保证金模式 全仓
    ccy = 'USDT'  # 保证金币种
    tra_side = 'buy'  # 单向持仓策略，BUY为买，SELL为卖
    tra_type = 'market'  # 策略交易类型LIMIT/MARKET

    all_amounts = 0  # 持仓数
    tra_price = 0.0  # 成交价格
    loss_x = 0  # 亏损仓位**********************
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
    okx = ccxt.okx({
        'apiKey': 'dc767025-4c9e-4ff5-9828-b2f55ea79a15',
        'secret': 'EA0075E87C08D4D1EA52264952E3A29D',
        'password': 'Qtrade13148859484.',
        'timeout': 10000,
        'enableRateLimit': True
    })
    print('交易所当前时间:', okx.iso8601(okx.milliseconds()))

    # 加载市场数据
    okx_markets = okx.load_markets()

    # 调整开仓杠杆,逐全仓模式,输出资金信息,可在app上完成,机器会默认app上的状态

    # 进入策略,永不结束
    while True:

        # 获取行情数据（自动重试）
        ticker_data = fetch_ticker_price(okx, symbol, instType)
        tra_price = float(ticker_data['data'][0]['markPx'])

        # 更新目标点位,头仓按照追踪价格只需0.5f
        if tra_side == 'buy':
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
            ticker_data = fetch_ticker_price(okx, symbol, instType)
            price = float(ticker_data['data'][0]['markPx'])
            # print('价格:', price, '时间:' + okx.iso8601(okx.milliseconds()))

            # 追踪高低点,更新时连带更新止损点
            if tra_side == 'buy':
                if price > track_price_extremes:
                    track_price_extremes = price
                    loss_price = track_price_extremes - float_price
            elif tra_side == 'sell':
                if price < track_price_extremes:
                    track_price_extremes = price
                    loss_price = track_price_extremes + float_price

            # 仓位管理,如果做多
            if tra_side == 'buy':
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
                            sz = tra_amounts
                            if sz < min_amount:
                                sz = min_amount
                            order_params = {
                                'instId': instId,
                                'tdMode': tdMode,
                                'ccy': ccy,
                                'side': tra_side,
                                'ordType': tra_type,
                                'sz': str(sz),
                            }
                            order_res = create_order(okx, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)

                            all_amounts = all_amounts + sz

                            # 信息
                            print('   胜利！目前无亏损，追加了仓位:', sz)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                        # 有亏损，加亏损仓并更改标记
                        elif loss_x != 0:
                            sz = loss_x + tra_amounts
                            if sz < min_amount:
                                sz = min_amount
                            order_params = {
                                'instId': instId,
                                'tdMode': tdMode,
                                'ccy': ccy,
                                'side': tra_side,
                                'ordType': tra_type,
                                'sz': str(sz),
                            }
                            order_res = create_order(okx, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)

                            all_amounts = all_amounts + sz
                            have_plus_loss = 1

                            # 信息
                            print('   胜利！有亏损，追加了仓位:', sz)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                    # 已经添加了亏损仓
                    else:
                        # 止盈亏损仓，将亏损设置为0,并设置没有添加亏损,在添加一份底仓
                        if loss_x > tra_amounts:
                            sz = loss_x - tra_amounts
                            if sz < min_amount:
                                sz = min_amount
                            order_params = {
                                'instId': instId,
                                'tdMode': tdMode,
                                'ccy': ccy,
                                'side': 'sell',
                                'ordType': tra_type,
                                'sz': str(sz),
                            }
                            order_res = create_order(okx, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)
                            all_amounts = all_amounts - sz
                        elif loss_x < tra_amounts:
                            sz = tra_amounts - loss_x
                            if sz < min_amount:
                                sz = min_amount
                            order_params = {
                                'instId': instId,
                                'tdMode': tdMode,
                                'ccy': ccy,
                                'side': 'buy',
                                'ordType': tra_type,
                                'sz': str(sz),
                            }
                            order_res = create_order(okx, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)
                            all_amounts = all_amounts + sz

                        have_plus_loss = 0

                        # 信息
                        print('   胜利中的胜利！已平亏损仓位:', loss_x, '   再次追加：', tra_amounts)
                        print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                        loss_x = 0

                # 价格小于失败价
                elif price < loss_price:
                    # 失败了，清仓改方向
                    tra_side = 'sell'
                    # 清仓等待下次机会
                    if all_amounts != 0:
                        sz = all_amounts
                        if sz < min_amount:
                            sz = min_amount
                        order_params = {
                            'instId': instId,
                            'tdMode': tdMode,
                            'ccy': ccy,
                            'side': tra_side,
                            'ordType': tra_type,
                            'sz': str(sz),
                        }
                        order_res = create_order(okx, order_params)
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

            elif tra_side == 'sell':
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
                            sz = tra_amounts
                            if sz < min_amount:
                                sz = min_amount
                            order_params = {
                                'instId': instId,
                                'tdMode': tdMode,
                                'ccy': ccy,
                                'side': tra_side,
                                'ordType': tra_type,
                                'sz': str(tra_amounts),
                            }
                            order_res = create_order(okx, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)

                            all_amounts = all_amounts + sz

                            # 信息
                            print('   胜利！目前无亏损，追加了仓位:', sz)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                        # 有亏损，加亏损仓并更改标记
                        elif loss_x != 0:
                            sz = loss_x + tra_amounts
                            if sz < min_amount:
                                sz = min_amount
                            order_params = {
                                'instId': instId,
                                'tdMode': tdMode,
                                'ccy': ccy,
                                'side': tra_side,
                                'ordType': tra_type,
                                'sz': str(sz),
                            }
                            order_res = create_order(okx, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)

                            all_amounts = all_amounts + sz
                            have_plus_loss = 1

                            # 信息
                            print('   胜利！有亏损，追加了仓位:', sz)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                    # 已经添加了亏损仓
                    else:
                        # 止盈亏损仓,将亏损设置为0，并设置没有添加亏损,在添加一份底仓
                        if loss_x > tra_amounts:
                            sz = loss_x - tra_amounts
                            if sz < min_amount:
                                sz = min_amount
                            order_params = {
                                'instId': instId,
                                'tdMode': tdMode,
                                'ccy': ccy,
                                'side': 'buy',
                                'ordType': tra_type,
                                'sz': str(sz),
                            }
                            order_res = create_order(okx, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)
                            all_amounts = all_amounts - sz
                        elif loss_x < tra_amounts:
                            sz = tra_amounts - loss_x
                            if sz < min_amount:
                                sz = min_amount
                            order_params = {
                                'instId': instId,
                                'tdMode': tdMode,
                                'ccy': ccy,
                                'side': 'sell',
                                'ordType': tra_type,
                                'sz': str(sz),
                            }
                            order_res = create_order(okx, order_params)
                            # 沉睡两秒模拟查询订单，给服务器处理响应时间以免大波动失控翻倍
                            time.sleep(2)
                            all_amounts = all_amounts + sz

                        have_plus_loss = 0

                        # 信息
                        print('   胜利中的胜利！已平亏损仓位:', loss_x, '   再次追加：', tra_amounts)
                        print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                        loss_x = 0

                # 价格大于失败价
                elif price > loss_price:
                    # 失败了，清仓改方向
                    tra_side = 'buy'
                    # 清仓等待下次机会
                    if all_amounts != 0:
                        sz = all_amounts
                        if sz < min_amount:
                            sz = min_amount
                        order_params = {
                            'instId': instId,
                            'tdMode': tdMode,
                            'ccy': ccy,
                            'side': tra_side,
                            'ordType': tra_type,
                            'sz': str(sz),
                        }
                        order_res = create_order(okx, order_params)
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
