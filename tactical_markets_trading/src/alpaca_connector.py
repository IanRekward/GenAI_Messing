import os
from pathlib import Path

from alpaca.trading.client import TradingClient
from dotenv import load_dotenv


def load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        raise FileNotFoundError(f".env not found at {env_path}")
    load_dotenv(env_path)
    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret_key:
        raise RuntimeError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in .env")
    return api_key, secret_key


def trading_client():
    api_key, secret_key = load_env()
    return TradingClient(api_key=api_key, secret_key=secret_key, paper=True)


if __name__ == "__main__":
    client = trading_client()
    account = client.get_account()
    print("--- Alpaca paper account ---")
    print(f"Account number:  {account.account_number}")
    print(f"Status:          {account.status}")
    print(f"Currency:        {account.currency}")
    print(f"Cash:            ${account.cash}")
    print(f"Buying power:    ${account.buying_power}")
    print(f"Equity:          ${account.equity}")
    print(f"Pattern day trader:    {account.pattern_day_trader}")
    print(f"Trading blocked: {account.trading_blocked}")
