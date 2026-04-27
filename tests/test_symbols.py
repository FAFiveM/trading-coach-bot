from coachbot.utils.symbols import parse_symbol


def test_crypto_usdt():
    inst = parse_symbol("BTCUSDT")
    assert inst.market == "crypto"
    assert inst.base == "BTC"
    assert inst.quote == "USDT"
    assert inst.ccxt_symbol == "BTC/USDT"


def test_forex_pair():
    inst = parse_symbol("EURUSD")
    assert inst.market == "forex"
    assert inst.base == "EUR"
    assert inst.quote == "USD"
    assert inst.yf_symbol == "EURUSD=X"


def test_with_slash():
    inst = parse_symbol("ETH/USDT")
    assert inst.market == "crypto"
    assert inst.ccxt_symbol == "ETH/USDT"


def test_xauusd():
    inst = parse_symbol("XAUUSD")
    assert inst.market == "commodity"
    assert inst.base == "XAU"
    assert inst.quote == "USD"
