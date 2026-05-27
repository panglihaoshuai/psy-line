"""Retail Investor Behavior Model.

基于行为金融学研究的行为模式识别:
- FOMO (Fear of Missing Out)
- Herding (从众行为)
- Disposition Effect (处置效应)
- Pump & Dump 检测

References:
- "All are investing in Crypto, I fear of being missed out" (Springer 2023)
- "Herding behavior in cryptocurrency markets" (arXiv:1806.11348)
- "Are Cryptos Different? Evidence from Retail Trading" (NBER 2023)
- "Exploring investor behavior in Bitcoin" (Digital Finance 2023)
- "Microstructure and Manipulation: Pump-and-Dump Dynamics" (arXiv:2504.15790)
"""

from enum import Enum
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING
from datetime import datetime

if TYPE_CHECKING:
    from .market_state import MarketState


class BehaviorPhase(str, Enum):
    """散户行为阶段"""
    SUSPICION = "suspicion"           # 上涨初期怀疑
    FOMO_BUY = "fomo_buy"             # FOMO追入
    PANIC_SELL = "panic_sell"          # 恐慌抛售
    CAPITULATION = "capitulation"      # 割肉离场
    EQUILIBRIUM = "equilibrium"        # 均衡状态
    FOMO_EXTREME = "fomo_extreme"      # 极度FOMO


@dataclass
class BehaviorIndicators:
    """行为指标"""
    # 价格动量
    price_momentum: float           # 价格动量 (-1 to 1)
    consecutive_up_days: int         # 连续上涨天数
    consecutive_down_days: int        # 连续下跌天数
    momentum_acceleration: float       # 动量加速度 (第二导数)

    # 波动性
    volatility: float                # 波动率
    volume_ratio: float              # 放量/缩量比率
    price_spread: float              # 价格振幅

    # 行为信号
    fomo_score: float               # FOMO指数 (0-1)
    herding_score: float             # 从众指数 (0-1)
    disposition_score: float          # 处置效应指数 (0-1)
    panic_score: float               # 恐慌指数 (0-1)

    # 时间戳
    timestamp: datetime


@dataclass
class BehaviorSignal:
    """行为信号"""
    phase: BehaviorPhase
    confidence: float               # 置信度 (0-1)
    narrative: str                   # 行为叙述
    indicators: BehaviorIndicators
    warnings: List[str]              # 警告信号
    timestamp: datetime

    def sentiment_adjustment(self) -> float:
        """
        将行为信号转换为情绪调整值 (-1 to 1)

        用于调整综合情绪分数
        """
        adjustments = {
            BehaviorPhase.SUSPICION: 0.1,      # 轻微看多（怀疑意味着可能上涨）
            BehaviorPhase.FOMO_BUY: -0.3,       # 轻度看空（FOMO买入是反向信号）
            BehaviorPhase.PANIC_SELL: 0.2,      # 轻度看多（恐慌抛售可能是买入机会）
            BehaviorPhase.CAPITULATION: 0.4,      # 强烈看多（极度悲观是买入信号）
            BehaviorPhase.EQUILIBRIUM: 0.0,     # 中性
            BehaviorPhase.FOMO_EXTREME: -0.5,   # 极度看空（极度FOMO是卖出信号）
        }
        return adjustments.get(self.phase, 0.0) * self.confidence


class RetailBehaviorModel:
    """
    散户行为识别模型

    检测散户交易行为模式:
    1. 上涨初期怀疑 -> 可能是吸筹
    2. 大涨FOMO买入 -> 可能是泡沫顶部
    3. 急跌恐慌抛售 -> 可能是假突破
    4. 连续大涨FOMO -> 极端贪婪
    5. 连续大跌割肉 -> 极端恐惧
    """

    def __init__(
        self,
        fomo_threshold: float = 0.7,
        panic_threshold: float = 0.6,
        herding_threshold: float = 0.65,
    ):
        """
        初始化行为模型

        Args:
            fomo_threshold: FOMO触发阈值
            panic_threshold: 恐慌触发阈值
            herding_threshold: 从众触发阈值
        """
        self.fomo_threshold = fomo_threshold
        self.panic_threshold = panic_threshold
        self.herding_threshold = herding_threshold

    def calculate_indicators(
        self,
        prices: List[float],
        volumes: Optional[List[float]] = None,
        lookback: int = 20,
    ) -> BehaviorIndicators:
        """
        计算行为指标

        Args:
            prices: 价格序列
            volumes: 成交量序列（可选）
            lookback: 回看周期

        Returns:
            BehaviorIndicators对象
        """
        if len(prices) < 3:
            return self._default_indicators()

        recent = prices[-lookback:]
        if len(recent) < 2:
            return self._default_indicators()

        # 价格动量
        price_change = (recent[-1] - recent[0]) / recent[0] if recent[0] != 0 else 0
        price_momentum = max(-1, min(1, price_change * 10))  # 归一化

        # 连续上涨/下跌天数
        consecutive_up = 0
        consecutive_down = 0
        for i in range(len(recent) - 1, 0, -1):
            if recent[i] > recent[i - 1]:
                consecutive_up += 1
            elif recent[i] < recent[i - 1]:
                consecutive_down += 1
            else:
                break

        # 动量加速度 (简单版: 价格上涨/下跌趋势的变化)
        if len(recent) >= 5:
            first_half_momentum = (recent[len(recent)//2] - recent[0]) / recent[0] if recent[0] != 0 else 0
            second_half_momentum = (recent[-1] - recent[len(recent)//2]) / recent[len(recent)//2] if recent[len(recent)//2] != 0 else 0
            momentum_acceleration = second_half_momentum - first_half_momentum
        else:
            momentum_acceleration = 0.0

        # 波动率 (标准差)
        import statistics
        volatility = statistics.stdev(recent) / statistics.mean(recent) if statistics.mean(recent) != 0 else 0

        # 成交量比率 (如果提供)
        volume_ratio = 1.0
        if volumes and len(volumes) >= lookback:
            recent_volumes = volumes[-lookback:]
            avg_volume = sum(recent_volumes) / len(recent_volumes)
            current_volume = recent_volumes[-1]
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

        # 价格振幅
        price_spread = (max(recent) - min(recent)) / statistics.mean(recent) if statistics.mean(recent) != 0 else 0

        # FOMO指数 (基于连续上涨和动量)
        fomo_score = self._calculate_fomo(
            consecutive_up, price_momentum, momentum_acceleration
        )

        # 从众指数
        herding_score = self._calculate_herding(
            consecutive_up, consecutive_down, volume_ratio
        )

        # 处置效应指数
        disposition_score = self._calculate_disposition(
            consecutive_up, consecutive_down, price_momentum
        )

        # 恐慌指数
        panic_score = self._calculate_panic(
            consecutive_down, volatility, volume_ratio, price_spread
        )

        return BehaviorIndicators(
            price_momentum=price_momentum,
            consecutive_up_days=consecutive_up,
            consecutive_down_days=consecutive_down,
            momentum_acceleration=momentum_acceleration,
            volatility=volatility,
            volume_ratio=volume_ratio,
            price_spread=price_spread,
            fomo_score=fomo_score,
            herding_score=herding_score,
            disposition_score=disposition_score,
            panic_score=panic_score,
            timestamp=datetime.now(),
        )

    def _calculate_fomo(
        self,
        consecutive_up: int,
        momentum: float,
        acceleration: float,
    ) -> float:
        """计算FOMO指数"""
        score = 0.0

        # 连续上涨天数贡献
        if consecutive_up >= 5:
            score += 0.4
        elif consecutive_up >= 3:
            score += 0.25
        elif consecutive_up >= 2:
            score += 0.15

        # 正向动量贡献
        if momentum > 0.1:
            score += 0.3
        elif momentum > 0.05:
            score += 0.2

        # 动量加速贡献
        if acceleration > 0.02:
            score += 0.3
        elif acceleration > 0:
            score += 0.15

        return min(1.0, score)

    def _calculate_herding(
        self,
        consecutive_up: int,
        consecutive_down: int,
        volume_ratio: float,
    ) -> float:
        """计算从众指数"""
        score = 0.0

        # 单边趋势贡献
        if consecutive_up >= 4 or consecutive_down >= 4:
            score += 0.4

        # 放量配合趋势
        if volume_ratio > 1.5:
            score += 0.4
        elif volume_ratio > 1.2:
            score += 0.2

        return min(1.0, score)

    def _calculate_disposition(
        self,
        consecutive_up: int,
        consecutive_down: int,
        momentum: float,
    ) -> float:
        """
        计算处置效应指数

        处置效应 = 卖出盈利、持有亏损
        在牛市中更明显
        """
        score = 0.0

        # 上涨后不卖（持有亏损等待回本）
        if momentum > 0.05 and consecutive_up < 3:
            score += 0.3

        # 下跌后恐慌卖出
        if consecutive_down >= 3 and momentum < -0.05:
            score += 0.4

        return min(1.0, score)

    def _calculate_panic(
        self,
        consecutive_down: int,
        volatility: float,
        volume_ratio: float,
        price_spread: float,
    ) -> float:
        """计算恐慌指数"""
        score = 0.0

        # 连续下跌贡献
        if consecutive_down >= 4:
            score += 0.35
        elif consecutive_down >= 2:
            score += 0.2

        # 高波动贡献
        if volatility > 0.05:
            score += 0.25

        # 放量下跌
        if volume_ratio > 1.5 and consecutive_down > 0:
            score += 0.25

        # 大振幅
        if price_spread > 0.1:
            score += 0.15

        return min(1.0, score)

    def _default_indicators(self) -> BehaviorIndicators:
        """返回默认指标"""
        return BehaviorIndicators(
            price_momentum=0.0,
            consecutive_up_days=0,
            consecutive_down_days=0,
            momentum_acceleration=0.0,
            volatility=0.0,
            volume_ratio=1.0,
            price_spread=0.0,
            fomo_score=0.0,
            herding_score=0.0,
            disposition_score=0.0,
            panic_score=0.0,
            timestamp=datetime.now(),
        )

    def detect_phase(
        self,
        indicators: BehaviorIndicators,
    ) -> BehaviorSignal:
        """
        检测当前行为阶段

        Returns:
            BehaviorSignal对象
        """
        warnings = []
        phase = BehaviorPhase.EQUILIBRIUM
        confidence = 0.5

        # 极度FOMO检测
        if indicators.fomo_score > 0.8 and indicators.consecutive_up_days >= 5:
            phase = BehaviorPhase.FOMO_EXTREME
            confidence = min(1.0, indicators.fomo_score)
            warnings.append("⚠️ 极度FOMO警告：可能接近顶部")
            warnings.append("历史数据显示FOMO极端期后往往有大幅回调")

        # FOMO Buy检测
        elif indicators.fomo_score > self.fomo_threshold and indicators.momentum_acceleration > 0:
            phase = BehaviorPhase.FOMO_BUY
            confidence = min(1.0, indicators.fomo_score)
            warnings.append("⚠️ FOMO买入信号：散户正在追高")
            warnings.append("反向指标：机构可能在派发")

        # Panic Sell检测
        elif indicators.panic_score > self.panic_threshold:
            phase = BehaviorPhase.PANIC_SELL
            confidence = min(1.0, indicators.panic_score)
            warnings.append("⚠️ 恐慌抛售信号：可能是假突破")
            warnings.append("历史数据显示恐慌卖出发后价格往往快速反弹")

        # Capitulation检测
        elif indicators.consecutive_down_days >= 6 and indicators.panic_score > 0.4:
            phase = BehaviorPhase.CAPITULATION
            confidence = 0.7
            warnings.append("🔴 极度悲观/割肉阶段")
            warnings.append("这是潜在的历史底部区域")

        # Suspicion检测 (上涨初期)
        elif indicators.consecutive_up_days >= 2 and indicators.consecutive_up_days <= 4:
            if indicators.herding_score < 0.3:
                phase = BehaviorPhase.SUSPICION
                confidence = 0.6
                warnings.append("💡 怀疑阶段：可能是吸筹期")

        # 叙述生成
        narratives = {
            BehaviorPhase.SUSPICION: (
                f"价格上涨初期，散户普遍怀疑。这通常发生在{indicators.consecutive_up_days}连涨后。"
                "机构可能在吸筹，散户在犹豫是否入场。"
            ),
            BehaviorPhase.FOMO_BUY: (
                f"FOMO驱动买入！连续{indicators.consecutive_up_days}天上涨，"
                f"FOMO指数{indicators.fomo_score:.0%}。"
                "这是反向信号——当所有人都在买时，风险大于机会。"
            ),
            BehaviorPhase.PANIC_SELL: (
                f"恐慌抛售！连续{indicators.consecutive_down_days}天下跌，"
                f"恐慌指数{indicators.panic_score:.0%}。"
                "但历史表明，这往往是买入机会而非卖出时机。"
            ),
            BehaviorPhase.CAPITULATION: (
                f"极度悲观阶段。连续{indicators.consecutive_down_days}天下跌，"
                "散户正在割肉离场。这通常是市场底部信号。"
            ),
            BehaviorPhase.EQUILIBRIUM: (
                "市场处于均衡状态，没有明显的散户行为极端信号。"
            ),
            BehaviorPhase.FOMO_EXTREME: (
                f"🔴 极度FOMO！连续{indicators.consecutive_up_days}天上涨，"
                f"FOMO指数{indicators.fomo_score:.0%}，处置效应{indicators.disposition_score:.0%}。"
                "极度贪婪信号，市场可能即将回调。"
            ),
        }

        return BehaviorSignal(
            phase=phase,
            confidence=confidence,
            narrative=narratives.get(phase, ""),
            indicators=indicators,
            warnings=warnings,
            timestamp=datetime.now(),
        )

    def get_trading_signal(
        self,
        behavior_signal: BehaviorSignal,
        base_sentiment: float,
    ) -> tuple[str, float]:
        """
        基于行为信号获取交易建议

        Args:
            behavior_signal: 行为信号
            base_sentiment: 基础情绪分数

        Returns:
            (signal_type, adjusted_sentiment)
        """
        adjustment = behavior_signal.sentiment_adjustment()
        adjusted = base_sentiment + adjustment

        # 边界处理
        adjusted = max(-1.0, min(1.0, adjusted))

        # 极端FOMO情况下强化卖出信号
        if behavior_signal.phase == BehaviorPhase.FOMO_EXTREME:
            return "SELL", adjusted

        # 极度悲观情况下强化买入信号
        if behavior_signal.phase == BehaviorPhase.CAPITULATION:
            return "BUY", adjusted

        # 其他阶段直接返回调整后的情绪
        if adjusted > 0.3:
            return "SELL", adjusted
        elif adjusted < -0.3:
            return "BUY", adjusted
        else:
            return "HOLD", adjusted

    def analyze_market_state(
        self,
        market_state: "MarketState",
    ) -> BehaviorSignal:
        """
        Analyze behavior phase from unified MarketState.

        Uses ALL data sources for cross-validation:
        - Price/volume data (existing logic)
        - Fear & Greed Index (fear confirmation)
        - Reddit sentiment (social confirmation)
        - Google Trends (search interest = FOMO signal)

        Args:
            market_state: Unified market state from all sources

        Returns:
            BehaviorSignal with cross-validated phase detection
        """
        # Step 1: Calculate base indicators from price data
        prices = [k.close for k in market_state.binance_klines]
        volumes = [k.volume for k in market_state.binance_klines]
        indicators = self.calculate_indicators(prices, volumes)

        # Step 2: Cross-validate with social sentiment
        # Fear & Greed confirmation
        if market_state.fear_greed_score is not None:
            fg = market_state.fear_greed_score  # -1 to 1
            if fg < -0.5:  # Extreme fear
                indicators.panic_score = min(1.0, indicators.panic_score + 0.2)
            elif fg > 0.5:  # Extreme greed
                indicators.fomo_score = min(1.0, indicators.fomo_score + 0.2)

        # Reddit sentiment confirmation
        if market_state.reddit_composite_score is not None:
            reddit = market_state.reddit_composite_score  # -1 to 1
            if reddit > 0.4:  # Strong bullish sentiment
                indicators.herding_score = min(1.0, indicators.herding_score + 0.15)
                indicators.fomo_score = min(1.0, indicators.fomo_score + 0.1)
            elif reddit < -0.4:  # Strong bearish sentiment
                indicators.panic_score = min(1.0, indicators.panic_score + 0.15)

        # Google Trends confirmation (high search = FOMO)
        if market_state.google_trends_score is not None:
            trends = market_state.google_trends_score  # -0.5 to 0.5
            if trends > 0.2:  # High search interest
                indicators.fomo_score = min(1.0, indicators.fomo_score + 0.15)
                indicators.herding_score = min(1.0, indicators.herding_score + 0.1)

        # Step 3: Detect phase with cross-validated indicators
        signal = self.detect_phase(indicators)

        # Step 4: Enhance narrative with social data
        if market_state.fear_greed_classification:
            signal.narrative += f"\nFear & Greed: {market_state.fear_greed_classification} ({market_state.fear_greed_value})"
        if market_state.reddit_composite_score is not None:
            signal.narrative += f"\nReddit sentiment: {market_state.reddit_composite_score:+.2f}"
        if market_state.google_trends_score is not None:
            signal.narrative += f"\nSearch interest: {market_state.google_trends_score:+.2f}"

        return signal
