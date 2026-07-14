from .base import Signal, Strategy
from .mean_reversion import MeanReversion
from .momentum import Momentum
from .trend_following import TrendFollowing

STRATEGIES = {
    "mean_reversion": MeanReversion,
    "momentum": Momentum,
    "trend_following": TrendFollowing,
}


def build(name: str, params: dict) -> Strategy:
    return STRATEGIES[name](params)
