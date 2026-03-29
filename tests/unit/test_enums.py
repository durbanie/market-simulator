"""Tests for core enums."""

import pytest

from market_simulator.core.enums import (
    Action,
    OrderStatus,
    OrderType,
    RejectionReason,
    Side,
)


class TestSide:
    def test_members(self):
        assert set(Side) == {Side.BUY, Side.SELL}

    def test_construction_from_string(self):
        assert Side("BUY") == Side.BUY
        assert Side("SELL") == Side.SELL

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            Side("INVALID")


class TestOrderType:
    def test_members(self):
        assert set(OrderType) == {OrderType.MARKET, OrderType.LIMIT}

    def test_construction_from_string(self):
        assert OrderType("MARKET") == OrderType.MARKET
        assert OrderType("LIMIT") == OrderType.LIMIT

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            OrderType("INVALID")


class TestOrderStatus:
    def test_members(self):
        expected = {
            OrderStatus.ACCEPTED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.FILLED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
        }
        assert set(OrderStatus) == expected

    def test_construction_from_string(self):
        assert OrderStatus("ACCEPTED") == OrderStatus.ACCEPTED
        assert OrderStatus("PARTIALLY_FILLED") == OrderStatus.PARTIALLY_FILLED
        assert OrderStatus("FILLED") == OrderStatus.FILLED
        assert OrderStatus("CANCELLED") == OrderStatus.CANCELLED
        assert OrderStatus("REJECTED") == OrderStatus.REJECTED

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            OrderStatus("INVALID")


class TestRejectionReason:
    def test_members(self):
        expected = {
            RejectionReason.UNREGISTERED_PARTICIPANT,
            RejectionReason.UNSUPPORTED_INSTRUMENT,
            RejectionReason.UNSUPPORTED_ORDER_TYPE,
            RejectionReason.NON_POSITIVE_PRICE,
            RejectionReason.NON_POSITIVE_QUANTITY,
            RejectionReason.EXCHANGE_CLOSED,
            RejectionReason.NO_LIQUIDITY,
        }
        assert set(RejectionReason) == expected

    def test_construction_from_string(self):
        for member in RejectionReason:
            assert RejectionReason(member.value) == member

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            RejectionReason("INVALID")


class TestAction:
    def test_members(self):
        assert set(Action) == {Action.SUBMIT, Action.MODIFY, Action.CANCEL}

    def test_construction_from_string(self):
        assert Action("SUBMIT") == Action.SUBMIT
        assert Action("MODIFY") == Action.MODIFY
        assert Action("CANCEL") == Action.CANCEL

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            Action("INVALID")
