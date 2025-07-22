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
    filename='bitget_trading_errors.log',
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
                except ccxt.RequestTimeout as e:
                    wait_time = delay * (attempt + 1)
                    print(f"请求超时，重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                    time.sleep(wait_time)
                except ccxt.BaseError as e:
                    # 解析错误码（使用正则表达式方案）
                    error_code = parse_error_code(e)
                    # print('错误码', error_code)
                    error_code = int(error_code)

                    if error_code == 40018:  # Bybit 的 IP 不匹配错误码
                        wait_time = delay * (attempt + 1)
                        print(f"错误码 {error_code}，API绑定IP错误！重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                        time.sleep(wait_time)
                        # 这类错误无法通过重试解决，考虑直接终止，但是bitget偶尔抽风

                    # 处理可重试的错误（如服务器过载、超时等）
                    elif error_code in [40010, 40015] and attempt < max_retries - 1:
                        wait_time = delay * (attempt + 1)
                        logging.warning(f"错误码 {error_code}，请求超时或系统异常，请稍后重试！重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                        print(f"错误码 {error_code}，请求超时或系统异常，请稍后重试！重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                        time.sleep(wait_time)
                    elif error_code == 40200 and attempt < max_retries - 1:
                        wait_time = delay * (attempt + 1)
                        logging.warning(f"错误码 {error_code}，服务器升级，请稍后再试！重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                        print(f"错误码 {error_code}，服务器升级，请稍后再试！重试第 {attempt + 1}/{max_retries} 次，等待 {wait_time} 秒")
                        time.sleep(wait_time)
                    else:
                        logging.error(f"操作失败：{e}")
                        raise

        return wrapper

    return decorator


# 错误码解析函数（正则方案）
def parse_error_code(e):
    raw_message = str(e)
    match = re.search(r'bitget\s*[:]?\s*({.*})', raw_message)
    if match:
        json_str = match.group(1)
        try:
            return json.loads(json_str).get('code')
        except json.JSONDecodeError:
            return None
    return None


# 查询合约指定币对价格
@retry(max_retries=100, delay=2)  # 最大重试100次，初始延迟2秒
def fetch_ticker_price(exchange, para_symbol, para_productType):
    return exchange.public_mix_get_v2_mix_market_ticker({'symbol': para_symbol, 'productType': para_productType})


# 合约下单
@retry(max_retries=100, delay=2)
def create_order(exchange, params):
    return exchange.private_mix_post_v2_mix_order_place_order(params)


if __name__ == '__main__':

    symbol = 'WCTUSDT'  # 要交易的币种************
    tra_amounts = 20.0  # 底仓数量*************
    float_price = 0.015  # 策略的加仓或平仓价格**********
    price_PRECISION = 4  # 此币的价格精度,小数点后几位**********
    min_amount = 10  # 此币最小下单数量************

    productType = 'USDT-FUTURES'  # 产品类型:u本位合约
    marginMode = 'crossed'  # 仓位模式全仓
    marginCoin = 'USDT'  # 保证币种
    tra_side = 'buy'  # 单向持仓策略，buy为买，sell为卖
    tra_type = 'market'  # 策略交易类型LIMIT/MARKET

    all_amounts = 0  # 持仓数
    tra_price = 0.0  # 成交价格
    loss_x = 0  # 亏损仓位
    win_price = 0  # 成功价格
    loss_price = 0  # 失败价格
    have_plus_loss = 0  # 是否添加了亏损仓位

    track_price_extremes = 0  # 追踪高低点,检测价格极限
    record_stop = 0  # 智能计算止损损失的仓位

    print('交易对:', symbol)
    print('底仓数量:', tra_amounts)
    print('单位浮动价格:', float_price)
    print('价格精度:', price_PRECISION)

    # 账号信息
    bitget = ccxt.bitget({
        'apiKey': 'bg_a65bf1649aa128bcf0ebc43a1d711586',
        'secret': '85c6e4dd9bc06b0688e6bb02c07a42b806da0fc7de5ecc23435dcdc5bf9219b2',
        'password': 'qtrade13148859484',
        'timeout': 10000,
        'enableRateLimit': True
    })
    print('交易所当前时间:', bitget.iso8601(bitget.milliseconds()))

    # 加载市场数据
    bitget_markets = bitget.load_markets()

    # 调整开仓杠杆,逐全仓模式,输出资金信息,可在app上完成,机器会默认app上的状态

    # 进入策略,永不结束
    while True:

        # 获取行情数据（自动重试）
        ticker_data = fetch_ticker_price(bitget, symbol, productType)
        tra_price = float(ticker_data['data'][0]['lastPr'])

        # 更新目标点位,头仓按照追踪价格只需0.5f
        if tra_side == 'buy':
            win_price = tra_price + float_price * 0.5
            loss_price = tra_price - float_price
            record_stop = loss_price
        else:
            win_price = tra_price - float_price * 0.5
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
            ticker_data = fetch_ticker_price(bitget, symbol, productType)
            price = float(ticker_data['data'][0]['lastPr'])
            # print('价格:', price, '时间:' + bybit.iso8601(bybit.milliseconds()))

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
                    win_price = win_price + float_price * 1.5
                    # 止损按照动态开单价格
                    loss_price = price - float_price
                    record_stop = loss_price

                    # 没有添加亏损仓
                    if have_plus_loss == 0:
                        # 没有亏损,相当于在这里开了底仓
                        if loss_x == 0:
                            size = tra_amounts
                            if size < min_amount:
                                size = min_amount
                            order_params = {
                                'symbol': symbol,
                                'productType': productType,
                                'marginMode': marginMode,
                                'marginCoin': marginCoin,
                                'size': str(size),  # 下单数量(基础币)
                                'side': tra_side,
                                'orderType': tra_type,
                            }
                            order_res = create_order(bitget, order_params)

                            all_amounts = all_amounts + size

                            # 信息
                            print('   胜利！目前无亏损，追加了仓位:', size)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                        # 有亏损，加亏损仓并更改标记
                        elif loss_x != 0:
                            size = loss_x + tra_amounts
                            if size < min_amount:
                                size = min_amount
                            order_params = {
                                'symbol': symbol,
                                'productType': productType,
                                'marginMode': marginMode,
                                'marginCoin': marginCoin,
                                'size': str(size),  # 下单数量(基础币)
                                'side': tra_side,
                                'orderType': tra_type,
                            }
                            order_res = create_order(bitget, order_params)

                            all_amounts = all_amounts + size
                            have_plus_loss = 1

                            # 信息
                            print('   胜利！有亏损，追加了仓位:', size)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                    # 已经添加了亏损仓
                    else:
                        # 止盈亏损仓，将亏损设置为0,并设置没有添加亏损,在添加一份底仓
                        if loss_x > tra_amounts:
                            size = loss_x - tra_amounts
                            if size < min_amount:
                                size = min_amount
                            order_params = {
                                'symbol': symbol,
                                'productType': productType,
                                'marginMode': marginMode,
                                'marginCoin': marginCoin,
                                'size': str(size),  # 下单数量(基础币)
                                'side': 'sell',
                                'orderType': tra_type,
                            }
                            order_res = create_order(bitget, order_params)
                            all_amounts = all_amounts - size
                        elif loss_x < tra_amounts:
                            size = tra_amounts - loss_x
                            if size < min_amount:
                                size = min_amount
                            order_params = {
                                'symbol': symbol,
                                'productType': productType,
                                'marginMode': marginMode,
                                'marginCoin': marginCoin,
                                'size': str(size),  # 下单数量(基础币)
                                'side': 'buy',
                                'orderType': tra_type,
                            }
                            order_res = create_order(bitget, order_params)
                            all_amounts = all_amounts + size

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
                        size = all_amounts
                        if size < min_amount:
                            size = min_amount
                        order_params = {
                            'symbol': symbol,
                            'productType': productType,
                            'marginMode': marginMode,
                            'marginCoin': marginCoin,
                            'size': str(size),  # 下单数量(基础币)
                            'side': tra_side,
                            'orderType': tra_type,
                        }
                        order_res = create_order(bitget, order_params)

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
                    loss_x = loss_x - int((loss_price - record_stop) * all_amounts / float_price)
                    if loss_x < 0:
                        loss_x = 0

                    # 已清仓
                    all_amounts = 0

                    i = 1  # break

            elif tra_side == 'sell':
                # 价格小于获胜价，胜利
                if price < win_price:
                    # 更新下个目标,并讨论有没有亏损仓
                    win_price = win_price - float_price * 1.5
                    # 止损按照动态开单价格
                    loss_price = price + float_price
                    record_stop = loss_price

                    # 没有添加亏损仓
                    if have_plus_loss == 0:
                        # 没有亏损,相当于在这里开了底仓
                        if loss_x == 0:
                            size = tra_amounts
                            if size < min_amount:
                                size = min_amount
                            order_params = {
                                'symbol': symbol,
                                'productType': productType,
                                'marginMode': marginMode,
                                'marginCoin': marginCoin,
                                'size': str(size),  # 下单数量(基础币)
                                'side': tra_side,
                                'orderType': tra_type,
                            }
                            order_res = create_order(bitget, order_params)

                            all_amounts = all_amounts + size

                            # 信息
                            print('   胜利！目前无亏损，追加了仓位:', size)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                        # 有亏损，加亏损仓并更改标记
                        elif loss_x != 0:
                            size = loss_x + tra_amounts
                            if size < min_amount:
                                size = min_amount
                            order_params = {
                                'symbol': symbol,
                                'productType': productType,
                                'marginMode': marginMode,
                                'marginCoin': marginCoin,
                                'size': str(size),  # 下单数量(基础币)
                                'side': tra_side,
                                'orderType': tra_type,
                            }
                            order_res = create_order(bitget, order_params)

                            all_amounts = all_amounts + size
                            have_plus_loss = 1

                            # 信息
                            print('   胜利！有亏损，追加了仓位:', size)
                            print('   目前持仓数量:', all_amounts, '  下个胜利:', win_price, '  失败止损:', loss_price)

                    # 已经添加了亏损仓
                    else:
                        # 止盈亏损仓,将亏损设置为0，并设置没有添加亏损,在添加一份底仓
                        if loss_x > tra_amounts:
                            size = loss_x - tra_amounts
                            if size < min_amount:
                                size = min_amount
                            order_params = {
                                'symbol': symbol,
                                'productType': productType,
                                'marginMode': marginMode,
                                'marginCoin': marginCoin,
                                'size': str(size),  # 下单数量(基础币)
                                'side': 'buy',
                                'orderType': tra_type,
                            }
                            order_res = create_order(bitget, order_params)
                            all_amounts = all_amounts - size
                        elif loss_x < tra_amounts:
                            size = tra_amounts - loss_x
                            if size < min_amount:
                                size = min_amount
                            order_params = {
                                'symbol': symbol,
                                'productType': productType,
                                'marginMode': marginMode,
                                'marginCoin': marginCoin,
                                'size': str(size),  # 下单数量(基础币)
                                'side': 'sell',
                                'orderType': tra_type,
                            }
                            order_res = create_order(bitget, order_params)
                            all_amounts = all_amounts + size

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
                        size = all_amounts
                        if size < min_amount:
                            size = min_amount
                        order_params = {
                            'symbol': symbol,
                            'productType': productType,
                            'marginMode': marginMode,
                            'marginCoin': marginCoin,
                            'size': str(size),  # 下单数量(基础币)
                            'side': tra_side,
                            'orderType': tra_type,
                        }
                        order_res = create_order(bitget, order_params)

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
                    loss_x = loss_x - int((record_stop - loss_price) * all_amounts / float_price)
                    if loss_x < 0:
                        loss_x = 0

                    # 已清仓
                    all_amounts = 0

                    i = 1  # break
