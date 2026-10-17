import threading

from agent_runtime.demo import DEMO_INPUT
from agent_runtime.store import SQLiteStore
from agent_runtime.wiring import build_runner


def test_two_workers_cannot_execute_the_same_step(config) -> None:
    runner = build_runner(config)
    waiting = runner.start(DEMO_INPUT)
    step = waiting.pending[0]
    runner.decide(waiting.run_id, step.step_id, "approve")
    calls = {"n": 0}
    lock = threading.Lock()
    real_execute = runner._tools.execute

    def counting(name: str, arguments: dict[str, object], run_id: str | None = None):
        if name == "send_refund":
            with lock:
                calls["n"] += 1
        return real_execute(name, arguments, run_id)

    runner._tools.execute = counting
    errors: list[BaseException] = []

    def work() -> None:
        try:
            runner.resume(waiting.run_id)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    store = SQLiteStore(config.database_path)
    assert calls["n"] == 1
    assert store.count_effects("send_refund") == 1
    refund = next(item for item in store.list_steps(waiting.run_id) if item.name == "send_refund")
    assert refund.attempt == 1
    assert refund.status == "succeeded"


def test_approving_twice_is_a_no_op(config) -> None:
    runner = build_runner(config)
    waiting = runner.start(DEMO_INPUT)
    step = waiting.pending[0]
    runner.decide(waiting.run_id, step.step_id, "approve")
    runner.decide(waiting.run_id, step.step_id, "approve")
    store = SQLiteStore(config.database_path)
    assert store.get_step(step.step_id).status == "approved"
    resumed = runner.resume(waiting.run_id)
    while resumed.status == "waiting_review" and resumed.pending:
        current = resumed.pending[0]
        runner.decide(resumed.run_id, current.step_id, "approve")
        runner.decide(resumed.run_id, current.step_id, "approve")
        resumed = runner.resume(resumed.run_id)
    assert resumed.status == "completed"
    assert store.count_effects("send_refund") == 1
    runner.decide(waiting.run_id, step.step_id, "approve")
    assert store.get_step(step.step_id).status == "succeeded"
