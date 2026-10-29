from petru.agent.cancel import Cancelled, CancelToken


def test_callbacks_run_once_and_late_ones_run_at_once():
    token, calls = CancelToken(), []
    remove = token.on_cancel(lambda: calls.append("a"))
    token.cancel()
    token.cancel()
    assert calls == ["a"] and token.cancelled
    token.on_cancel(lambda: calls.append("late"))
    assert calls == ["a", "late"]
    token.reset()
    assert not token.cancelled
    remove()
    token.cancel()
    assert calls == ["a", "late"]


def test_check_raises_only_once_cancelled():
    token = CancelToken()
    token.check()
    token.cancel()
    try:
        token.check()
    except Cancelled as exc:
        assert isinstance(exc, KeyboardInterrupt)
    else:
        raise AssertionError("check() did not raise")
